# Documentation

Start with [How it works](../HOW_IT_WORKS.md) for the overview. The pages are grouped by what you want to do.

## [architecture/](architecture/): how it works

| Page | What it covers |
|---|---|
| [The policy gate](architecture/policy-gate.md) | Allow, local or block: how each request is decided |
| [The decision model, policies and tests](architecture/decision-model.md) | Laya, the four policies, the test cases |
| [The agent](architecture/agent.md) | What happens to a message |
| [The UI](architecture/ui.md) | The web page, the gateway, the API |
| [Conversation history](architecture/conversation-history.md) | SQLite, and why local-only conversations stay local |

## [setup/](setup/): run it

| Page | What it covers |
|---|---|
| [Deployment](setup/deployment.md) | The pods, volumes and every setting |
| [Model choice](setup/model-choice.md) | Claude or the local model, and how to switch |
| [Windows (WSL2) setup](setup/wsl2.md) | k3s and Docker on WSL2 |

## [finetune/](finetune/): train the decision model

| Page | What it covers |
|---|---|
| [Fine-tuning](finetune/fine-tuning.md) | The data, the run, and loading the result |
| [Fine-tuning on an AWS GPU](finetune/aws-gpu.md) | Renting a GPU for the run |
| [Results](finetune/results.md) | What the gate catches, with and without the model |
