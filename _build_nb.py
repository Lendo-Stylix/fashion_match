import json, ast, os

secrets = json.load(open("/tmp/_secrets.json"))
NL = chr(10)
K = secrets["KAGGLE_API_KEY"]
W = secrets["WANDB_API_KEY"]

cell0 = NL.join([
    "# OutfitMatch Stylist - GRPO RL (verifiable rewards) on Kaggle T4 (16GB)",
    "# Logs ONLINE to W&B. API keys embedded per project policy (.env.local).",
    "import os, sys, subprocess, time, traceback",
    "",
    "os.environ['KAGGLE_API_KEY'] = '%s'" % K,
    "os.environ['WANDB_API_KEY'] = '%s'" % W,
    "os.environ['WANDB_MODE'] = 'online'",
    "os.environ['WANDB_PROJECT'] = 'outfitmatch-stylist'",
    "os.environ['WANDB_ENTITY'] = 'vominhnhatquang-fpt-university'",
    "os.environ['WANDB_SILENT'] = 'true'",
    "os.environ['HF_HUB_CACHE'] = '/kaggle/working/hf_cache'",
    "os.environ['HF_HOME'] = '/kaggle/working/hf_home'",
    "os.environ['BITSANDBYTES_NOWELCOME'] = '1'",
    "os.environ['PYTHONPATH'] = '/kaggle/working/fashion_match/src' + os.pathsep + os.environ.get('PYTHONPATH', '')",
    "print('secrets + env configured (WANDB_MODE=%s)' % os.environ['WANDB_MODE'])",
]) + NL

stub = [
    "import os",
    "os.makedirs('/kaggle/working/vllm_stub/vllm', exist_ok=True)",
    "with open('/kaggle/working/vllm_stub/vllm/__init__.py', 'w') as f:",
    "    f.write('class LLM:\\n')",
    "    f.write('    def __init__(self, *a, **k):\\n')",
    "    f.write('        raise RuntimeError(\"vllm disabled; GRPO uses HF generate()\")\\n')",
    "    f.write('class SamplingParams:\\n')",
    "    f.write('    def __init__(self, *a, **k):\\n')",
    "    f.write('        raise RuntimeError(\"vllm disabled\")\\n')",
    "print('vllm stub written')",
]
cell1 = NL.join([
    "# 1) Dep install. Pin trl 0.14.0 + transformers/accelerate (versions that worked for qlora).",
    "subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--force-reinstall', '--no-deps',",
    "                       'trl==0.14.0', 'transformers==4.57.3', 'accelerate==1.14.0',",
    "                       'bitsandbytes', 'peft', 'datasets', 'wandb'])",
    "# trl 0.14 imports `from vllm import LLM, SamplingParams` at top-level behind a broken",
    "# is_vllm_available() tuple. Stub it so the import succeeds; GRPO uses use_vllm=False.",
    NL.join(stub),
    "sys.path.insert(0, '/kaggle/working/vllm_stub')",
    "print('deps installed + vllm stub added')",
]) + NL

cell2 = NL.join([
    "# 2) Fetch code + IDEMPOTENT patch so --report-to/--wandb-* always work (safety net).",
    "REPO = 'https://github.com/Lendo-Stylix/fashion_match.git'",
    "BRANCH = 'feat/benchmark'",
    "root = '/kaggle/working/fashion_match'",
    "if not os.path.isdir(os.path.join(root, '.git')):",
    "    subprocess.check_call(['git', 'clone', '--depth', '1', '-b', BRANCH, REPO, root])",
    "script = os.path.join(root, 'scripts', 'stylist', 'train_grpo_kaggle.py')",
    "src = open(script, encoding='utf-8').read()",
    "anchor1 = '    parser.add_argument(\"--push-to-hub\", default=None, help=\"HF repo id to push adapter\")'",
    "new_args = anchor1 + chr(10) + '    parser.add_argument(\"--report-to\", default=\"none\", help=\"W&B logger target (wandb/none).\")' + chr(10) + '    parser.add_argument(\"--wandb-project\", default=\"outfitmatch-stylist\")' + chr(10) + '    parser.add_argument(\"--wandb-run-name\", default=None)'",
    "if 'report-to' not in src:",
    "    assert anchor1 in src, 'clone missing push-to-hub anchor'",
    "    src = src.replace(anchor1, new_args)",
    "anchor2 = '        seed=args.seed,'",
    "new_cfg = '        seed=args.seed,' + chr(10) + '        report_to=args.report_to,' + chr(10) + '        run_name=args.wandb_run_name,'",
    "if 'report_to=args.report_to' not in src:",
    "    assert anchor2 in src, 'clone missing seed anchor'",
    "    src = src.replace(anchor2, new_cfg)",
    "open(script, 'w', encoding='utf-8').write(src)",
    "print('patched train script ok:', 'report-to' in src and 'report_to=args.report_to' in src)",
]) + NL

cell3 = NL.join([
    "# 3) Sanity: import reward module (verifies outfitmatch + scorers load) and build dataset.",
    "import sys",
    "sys.path.insert(0, '/kaggle/working/fashion_match/src')",
    "sys.path.insert(0, '/kaggle/working/fashion_match/scripts/stylist')",
    "from grpo_rewards import FASHION_REWARD_FUNCS, build_fashion_prompt_pool",
    "pool = build_fashion_prompt_pool()",
    "print('reward funcs:', [f.__name__ for f in FASHION_REWARD_FUNCS])",
    "print('pool size:', len(pool), 'types:', sorted({r['item_type'] for r in pool}))",
]) + NL

cell4 = (
    "# 4) GRPO RL run. T4 16GB fits bnb-4bit 8B + full 256-token completions (not truncated).\n"
    "#    Run via runpy so the REAL training traceback surfaces for diagnostics.\n"
    "#    --report-to wandb -> trl/transformers call wandb.init() ONLINE (WANDB_API_KEY set).\n"
    "import runpy\n"
    "MAX_STEPS = int(os.environ.get('GRPO_MAX_STEPS', '500'))\n"
    "sys.path.insert(0, '/kaggle/working/fashion_match')\n"
    "sys.path.insert(0, '/kaggle/working/fashion_match/scripts/stylist')\n"
    "argv = ['train_grpo_kaggle.py',\n"
    "        '--model', 'unsloth/Qwen3-VL-8B-Instruct-bnb-4bit',\n"
    "        '--report-to', 'wandb',\n"
    "        '--wandb-project', 'outfitmatch-stylist',\n"
    "        '--wandb-run-name', 'om-grpo-t4-instruct',\n"
    "        '--max-steps', str(MAX_STEPS),\n"
    "        '--num-generations', '8',\n"
    "        '--batch-size', '8',\n"
    "        '--max-completion-length', '256',\n"
    "        '--temperature', '0.7',\n"
    "        '--lora-r', '32',\n"
    "        '--think',\n"
    "        '--output-dir', '/kaggle/working/outputs/grpo-t4-instruct']\n"
    "sys.argv = argv\n"
    "print('Running:', ' '.join(argv))\n"
    "t0 = time.time()\n"
    "try:\n"
    "    runpy.run_path('/kaggle/working/fashion_match/scripts/stylist/train_grpo_kaggle.py', run_name='__main__')\n"
    "except SystemExit as e:\n"
    "    print('train exited with code', e.code)\n"
    "    raise\n"
    "print('GRPO finished in %.1f min' % ((time.time() - t0) / 60))\n"
)

cell5 = NL.join([
    "# 5) Persist artifacts: zip the LoRA adapter so it appears in notebook output files (downloadable).",
    "import shutil",
    "out_root = '/kaggle/working/outputs/grpo-t4-instruct'",
    "if os.path.isdir(out_root):",
    "    zip_path = '/kaggle/working/grpo-t4-instruct-adapter.zip'",
    "    shutil.make_archive(zip_path[:-4], 'zip', out_root)",
    "    print('adapter zipped ->', zip_path, 'size MB=%.1f' % (os.path.getsize(zip_path)/1e6))",
    "    print('adapter files:', sorted(os.listdir(out_root))[:20])",
    "else:",
    "    print('WARNING: output dir missing, run may not have completed')",
]) + NL

cells = [cell0, cell1, cell2, cell3, cell4, cell5]
for i, c in enumerate(cells):
    ast.parse(c)

def code_cell(src):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": src.splitlines(keepends=True)}

nb = {"cells": [code_cell(c) for c in cells],
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                   "language_info": {"name": "python", "version": "3.12"}, "accelerator": "GPU"},
      "nbformat": 4, "nbformat_minor": 5}
out = "data/stylist/fine_tune/runs/kaggle_grpo_t4/notebook/grpo_stylist.ipynb"
json.dump(nb, open(out, "w"), indent=1)
print("notebook rebuilt, all", len(cells), "cells parse OK ->", out)
