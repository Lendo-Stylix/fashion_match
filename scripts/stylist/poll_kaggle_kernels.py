from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from kaggle.api.kaggle_api_extended import KaggleApi
from requests import HTTPError

DEFAULT_KERNELS = [
    "nhimchauphii/om-sty-t4qwen-0612-qwen3vl8b-instruct",
    "nhimchauphii/om-sty-t4qwen-0612-qwen35-9b",
]
TERMINAL_STATUSES = {
    "KernelWorkerStatus.COMPLETE",
    "KernelWorkerStatus.ERROR",
    "KernelWorkerStatus.CANCEL_ACKNOWLEDGED",
}
FINAL_ARTIFACT_BASENAMES = {"training_summary.json"}
DEFAULT_SAVE_DIR = "data/stylist/fine_tune/runs/kaggle_qlora_token3_t4_qwen"
DEFAULT_MANIFEST = Path(DEFAULT_SAVE_DIR) / "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll Kaggle kernel status, outputs, logs, and optional W&B live state."
    )
    parser.add_argument("kernels", nargs="*", default=DEFAULT_KERNELS)
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--token-env-var", default="KAGGLE_API_TOKEN_4")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--max-polls", type=int, default=0)
    parser.add_argument("--tail-lines", type=int, default=40)
    parser.add_argument("--save-dir", default=DEFAULT_SAVE_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--wandb-api-token-env-var", default="WANDB_API_TOKEN")
    parser.add_argument("--wandb-project", default="outfitmatch-stylist")
    parser.add_argument("--wandb-entity")
    return parser.parse_args()


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_value(name: str, env_file: Path) -> str | None:
    return os.environ.get(name) or read_env_file(env_file).get(name)


def require_value(name: str, env_file: Path) -> str:
    value = resolve_value(name, env_file)
    if value:
        return value
    raise SystemExit(f"Missing '{name}'. Set it in the environment or {env_file}.")


def build_api(token: str) -> KaggleApi:
    os.environ["KAGGLE_API_TOKEN"] = token
    api = KaggleApi()
    api.authenticate()
    return api


def safe_status(api: KaggleApi, kernel: str) -> tuple[str, str | None]:
    try:
        response = api.kernels_status(kernel)
    except HTTPError as exc:
        return f"HTTP_{getattr(exc.response, 'status_code', 'ERROR')}", str(exc)
    except ValueError as exc:
        return "ERROR", str(exc)
    return str(response.status), response.failure_message or None


def safe_logs(api: KaggleApi, kernel: str) -> str:
    try:
        return api.kernels_logs(kernel)
    except HTTPError as exc:
        return f"<failed to fetch logs: HTTP {getattr(exc.response, 'status_code', 'ERROR')} {exc}>"
    except ValueError as exc:
        return f"<failed to fetch logs: {exc}>"


def safe_list_files(
    api: KaggleApi, kernel: str, page_size: int = 100
) -> tuple[list[str], str | None]:
    try:
        page_token = None
        files: list[str] = []
        while True:
            page = api.kernels_list_files(kernel, page_token=page_token, page_size=page_size)
            page_files = getattr(page, "files", None) or []
            for item in page_files:
                name = getattr(item, "name", None) or getattr(item, "file_name", None)
                if name:
                    files.append(str(name))
            page_token = getattr(page, "next_page_token", None) or getattr(
                page, "nextPageToken", None
            )
            if not page_token:
                break
        return sorted(files), None
    except HTTPError as exc:
        return [], f"HTTP_{getattr(exc.response, 'status_code', 'ERROR')}: {exc}"
    except ValueError as exc:
        return [], str(exc)


def tail_lines(text: str, count: int) -> str:
    if count <= 0:
        return ""
    return "\n".join(text.splitlines()[-count:])


def slugify_kernel(kernel: str) -> str:
    return kernel.replace("/", "__")


def all_terminal(statuses: Iterable[str]) -> bool:
    return all(status in TERMINAL_STATUSES for status in statuses)


def has_final_artifact(files: Iterable[str]) -> bool:
    for name in files:
        normalized = name.replace("\\", "/")
        base = normalized.rsplit("/", 1)[-1]
        if base in FINAL_ARTIFACT_BASENAMES:
            return True
        if normalized.endswith(".zip"):
            return True
        if normalized.endswith("/adapter/adapter_model.safetensors"):
            return True
    return False


def extract_wandb_lines(logs: str, limit: int = 5) -> list[str]:
    return [line for line in logs.splitlines() if "wandb" in line.lower()][-limit:]


def wandb_hint(files: Iterable[str], logs: str) -> str:
    if any("wandb" in name.lower() for name in files):
        return "yes"
    if extract_wandb_lines(logs, limit=1):
        return "yes"
    return "no"


def load_manifest_run_names(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    mapping: dict[str, str] = {}
    for row in payload.get("kernels", []):
        if not isinstance(row, dict):
            continue
        kernel_id = row.get("kernel_id")
        run_id = row.get("run_id")
        if kernel_id and run_id:
            mapping[str(kernel_id)] = f"outfitmatch-{run_id}"
    return mapping


def build_wandb_api(api_token: str | None):
    if not api_token:
        return None
    os.environ["WANDB_API_KEY"] = api_token
    try:
        import wandb

        return wandb.Api()
    except Exception:
        return None


def resolve_wandb_entity(api: Any, explicit_entity: str | None) -> str:
    if explicit_entity:
        return explicit_entity
    return str(getattr(api, "default_entity", "") or "")


def lookup_wandb_run(
    api: Any, *, entity: str, project: str, run_name: str
) -> dict[str, Any] | None:
    if api is None or not entity or not project or not run_name:
        return None
    try:
        for run in api.runs(f"{entity}/{project}"):
            name = getattr(run, "name", None)
            display_name = getattr(run, "display_name", None)
            if run_name not in {name, display_name}:
                continue
            summary_obj = getattr(run, "summary", None)
            if hasattr(summary_obj, "_json_dict"):
                summary = dict(summary_obj._json_dict)
            elif isinstance(summary_obj, dict):
                summary = dict(summary_obj)
            else:
                summary = {}
            interesting = {
                key: summary[key]
                for key in (
                    "_step",
                    "train/global_step",
                    "train/loss",
                    "eval/loss",
                    "train/grad_norm",
                    "train/learning_rate",
                    "epoch",
                )
                if key in summary
            }
            gpu_metrics = {
                key: value
                for key, value in summary.items()
                if isinstance(key, str) and key.startswith("system.gpu")
            }
            return {
                "run_name": run_name,
                "state": getattr(run, "state", None),
                "url": getattr(run, "url", None),
                "project": project,
                "entity": entity,
                "metrics": interesting,
                "gpu_metrics": gpu_metrics,
            }
    except Exception:
        return None
    return None


def main() -> None:
    args = parse_args()
    env_file = Path(args.env_file)
    token = require_value(args.token_env_var, env_file)
    api = build_api(token)
    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    run_name_map = load_manifest_run_names(args.manifest)
    wandb_api = build_wandb_api(resolve_value(args.wandb_api_token_env_var, env_file))
    wandb_entity = resolve_wandb_entity(wandb_api, args.wandb_entity)

    last_logs: dict[str, str] = {}
    last_files: dict[str, set[str]] = {}
    poll_count = 0

    while True:
        poll_count += 1
        statuses: list[str] = []
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n=== Poll {poll_count} @ {stamp} ===", flush=True)
        for kernel in args.kernels:
            status, failure_message = safe_status(api, kernel)
            statuses.append(status)
            print(f"[{kernel}] status={status}", flush=True)
            if failure_message:
                print(f"[{kernel}] failure_message={failure_message}", flush=True)

            files, file_error = safe_list_files(api, kernel)
            file_set = set(files)
            new_files = sorted(file_set - last_files.get(kernel, set()))
            final_artifact = "yes" if has_final_artifact(files) else "no"
            print(f"[{kernel}] output_file_count={len(files)}", flush=True)
            print(f"[{kernel}] has_final_artifact={final_artifact}", flush=True)
            if file_error:
                print(f"[{kernel}] output_file_error={file_error}", flush=True)
            elif new_files:
                print(f"[{kernel}] new_files={len(new_files)}", flush=True)
                for name in new_files[:20]:
                    print(f"  + {name}", flush=True)
                if len(new_files) > 20:
                    print(f"  ... and {len(new_files) - 20} more", flush=True)
            elif kernel in last_files:
                print(f"[{kernel}] new_files=0", flush=True)
            last_files[kernel] = file_set

            files_path = save_dir / f"{slugify_kernel(kernel)}_remote_files.json"
            files_path.write_text(
                json.dumps(
                    {
                        "kernel": kernel,
                        "status": status,
                        "file_count": len(files),
                        "has_final_artifact": final_artifact == "yes",
                        "files": files,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"[{kernel}] remote_files_saved={files_path.as_posix()}", flush=True)

            logs = safe_logs(api, kernel)
            log_path = save_dir / f"{slugify_kernel(kernel)}_latest.log"
            log_path.write_text(logs, encoding="utf-8")
            if kernel not in last_logs or logs != last_logs[kernel]:
                snippet = tail_lines(logs, args.tail_lines)
                if snippet:
                    print(f"--- {kernel} log tail ({args.tail_lines} lines) ---", flush=True)
                    print(snippet, flush=True)
                else:
                    print(f"--- {kernel} log tail: <empty> ---", flush=True)
                last_logs[kernel] = logs
            print(f"[{kernel}] log_saved={log_path.as_posix()}", flush=True)

            w_hint = wandb_hint(files, logs)
            print(f"[{kernel}] wandb_hint={w_hint}", flush=True)
            for line in extract_wandb_lines(logs):
                print(f"  {line}", flush=True)

            run_name = run_name_map.get(kernel)
            wandb_snapshot = lookup_wandb_run(
                wandb_api,
                entity=wandb_entity,
                project=args.wandb_project or "",
                run_name=run_name or "",
            )
            if wandb_snapshot:
                print(
                    f"[{kernel}] wandb_status={wandb_snapshot['state']} "
                    f"wandb_url={wandb_snapshot['url']}",
                    flush=True,
                )
                if wandb_snapshot["metrics"]:
                    print(
                        f"[{kernel}] wandb_metrics="
                        f"{json.dumps(wandb_snapshot['metrics'], ensure_ascii=False)}",
                        flush=True,
                    )
                if wandb_snapshot["gpu_metrics"]:
                    subset = dict(list(wandb_snapshot["gpu_metrics"].items())[:6])
                    print(
                        f"[{kernel}] wandb_gpu_metrics={json.dumps(subset, ensure_ascii=False)}",
                        flush=True,
                    )
                wandb_path = save_dir / f"{slugify_kernel(kernel)}_wandb_status.json"
                wandb_path.write_text(
                    json.dumps(wandb_snapshot, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"[{kernel}] wandb_status_saved={wandb_path.as_posix()}", flush=True)

        if all_terminal(statuses):
            print("All kernels reached terminal status.", flush=True)
            return
        if args.max_polls and poll_count >= args.max_polls:
            print("Reached max polls before all kernels finished.", flush=True)
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
