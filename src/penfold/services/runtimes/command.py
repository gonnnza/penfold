"""Runtime que ejecuta comandos externos configurables sin invocar un shell."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import signal
from pathlib import Path

from penfold.errors import CancelledError, ExecutionError, PermissionDeniedError
from penfold.services.runtimes.base import AgentRuntime, RuntimeContext, RuntimeResult
from penfold.services.runtimes.secrets import redact

_SHELL_META = set(";&|`$><\n\r")


class CommandRuntime(AgentRuntime):
    name = "command"
    simulated = False

    async def validate(self) -> None:
        return None

    async def healthcheck(self) -> bool:
        # Cada comando se verifica al ejecutarse; no asumimos un binario común.
        return True

    async def execute(self, context: RuntimeContext) -> RuntimeResult:
        command = context.options.get("command")
        if not command and context.agent is not None:
            command = context.agent.runtime.command
        if not isinstance(command, str) or not command.strip():
            raise ExecutionError(
                "CommandRuntime requiere un comando en config.command o runtime.command."
            )
        if any(char in command for char in _SHELL_META):
            raise ExecutionError(
                "El comando contiene metacaracteres de shell (; & | ` $ > <). "
                "Penfold ejecuta comandos con exec directo, sin shell."
            )
        argv = shlex.split(command)
        if not argv:
            raise ExecutionError("El comando está vacío después de analizarlo.")

        permissions = context.options.get("permissions") or {}
        mode = permissions.get("mode", "workspace_write")
        if mode == "read_only":
            raise PermissionDeniedError(
                "El modo read_only no permite ejecutar comandos. "
                "Configura workspace_write o restricted para este nodo."
            )
        allowed = permissions.get("allowed_commands") or []
        binary = Path(argv[0]).name
        if mode == "restricted" and allowed and binary not in {Path(item).name for item in allowed}:
            raise PermissionDeniedError(
                f"Comando {binary!r} no permitido en modo restricted. Permitidos: {allowed}"
            )
        resolved_binary = shutil.which(argv[0])
        if resolved_binary is None:
            raise ExecutionError(f"No se encontró el ejecutable {argv[0]!r} en PATH.")

        workspace = context.workspace.resolve()
        cwd_raw = str(context.options.get("cwd", "."))
        cwd = (workspace / cwd_raw).resolve()
        if not cwd.is_relative_to(workspace):
            raise PermissionDeniedError(f"cwd {cwd_raw!r} está fuera del workspace autorizado.")
        if not cwd.is_dir():
            raise ExecutionError(f"cwd no existe o no es un directorio: {cwd}")

        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in (context.options.get("env") or {}).items()})

        process = await asyncio.create_subprocess_exec(
            resolved_binary,
            *argv[1:],
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        stdout_task = asyncio.create_task(
            process.stdout.read() if process.stdout else asyncio.sleep(0, result=b"")
        )
        stderr_task = asyncio.create_task(
            process.stderr.read() if process.stderr else asyncio.sleep(0, result=b"")
        )
        wait_task = asyncio.create_task(process.wait())
        cancel_task = asyncio.create_task(
            context.cancel_event.wait()
            if context.cancel_event is not None
            else asyncio.Event().wait()
        )
        timed_out = False
        cancelled = False
        try:
            done, _ = await asyncio.wait(
                [wait_task, cancel_task],
                timeout=context.timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_task in done and cancel_task.result():
                cancelled = True
            elif wait_task not in done:
                timed_out = True
        finally:
            for task in (wait_task, cancel_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(wait_task, cancel_task, return_exceptions=True)

        if cancelled or timed_out:
            self._terminate(process)
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except (TimeoutError, ProcessLookupError):  # pragma: no cover
                pass
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            if cancelled:
                raise CancelledError(f"Comando cancelado: {command}")
            raise ExecutionError(
                f"Timeout de {context.timeout}s al ejecutar: {command}. El proceso fue terminado."
            )

        raw_out, raw_err = await asyncio.gather(stdout_task, stderr_task)
        # Cerrar el transporte aquí evita que el colector de basura intente
        # cerrar pipes cuando el event loop (p. ej. el de TestClient) ya murió.
        transport = getattr(process, "_transport", None)
        if transport is not None:  # pragma: no cover - detalle de asyncio
            transport.close()
        max_chars = int(context.options.get("max_output_chars", 50000))
        stdout = redact(raw_out.decode("utf-8", errors="replace"))[:max_chars]
        stderr = redact(raw_err.decode("utf-8", errors="replace"))[:max_chars]
        exit_code = process.returncode if process.returncode is not None else -1

        artifacts: list[str] = []
        artifacts_dir = Path(
            context.options.get(
                "artifacts_dir", workspace / ".orchestrator" / "artifacts" / context.run_id
            )
        )
        try:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            for suffix, content in (("stdout.txt", stdout), ("stderr.txt", stderr)):
                target = artifacts_dir / f"{context.node_id}.{suffix}"
                target.write_text(content, encoding="utf-8")
                artifacts.append(str(target))
        except OSError:
            # Los artefactos son útiles pero no deben fallar la ejecución.
            pass

        return RuntimeResult(
            output={
                "command": command,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "passed": exit_code == 0,
            },
            logs=[f"[CMD] {command} -> exit_code={exit_code}"],
            artifacts=artifacts,
            metadata={"runtime": self.name, "binary": binary, "cwd": str(cwd)},
        )

    @staticmethod
    def _terminate(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                process.kill()
            except ProcessLookupError:  # pragma: no cover
                pass
