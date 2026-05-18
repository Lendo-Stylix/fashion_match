import os

# Force W&B offline so tests never hit the network
os.environ["WANDB_MODE"] = "offline"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
