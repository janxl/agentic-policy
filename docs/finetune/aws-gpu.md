[← How it works](../../HOW_IT_WORKS.md) · Fine-tuning

# Fine-tuning on an AWS GPU

[Fine-tuning](fine-tuning.md) wants a GPU, and a rented one is cheap for this: on an NVIDIA A10G the training
takes about 5 minutes, plus a few more for setup and the model download. This page is the steps for an AWS
instance.

1. **Quota.** New accounts often have a zero limit for GPU instances. In *Service Quotas* → EC2, request
   *Running On-Demand G and VT instances* of at least 4 vCPUs. It can take a day, and it is per region.
2. **Launch** a `g5.xlarge` (24 GB GPU) in a region with capacity (`us-east-1` and `us-west-2` are the
   safest), x86_64, with a *Deep Learning OSS Nvidia Driver AMI (PyTorch, Ubuntu)*. That image already has
   the NVIDIA driver and PyTorch. Check `python3 --version` is 3.11 or newer. Allow SSH from your IP only.
   If a region has no capacity, try another availability zone, a `g6.xlarge` or `g4dn.xlarge`, or another
   region (the AMI id and the quota are per region).
3. **Copy the code up**, only what the run needs (**not** the whole folder, which would put `secret.yaml`
   and your API key on the VM):

   ```bash
   cd agentic-policy
   ssh -i key.pem ubuntu@<host> "mkdir -p agentic-policy/finetune"
   scp -i key.pem -r laya agent policies.toml policy_cases.toml ubuntu@<host>:~/agentic-policy/
   scp -i key.pem finetune/*.py finetune/*.sh ubuntu@<host>:~/agentic-policy/finetune/
   ```

   The key file must not be readable by others. From WSL, keep it in your Linux home (`~/.ssh`) and
   `chmod 600` it: a key on the Windows drive always looks too open.
4. **Run it** inside `tmux`, so a dropped connection does not stop it:

   ```bash
   ssh -i key.pem ubuntu@<host>
   tmux new -s ft
   cd agentic-policy && bash finetune/run.sh
   ```

   The first line it prints says whether PyTorch sees the GPU. Press `Ctrl-b` then `d` to detach, and
   `tmux attach -t ft` to come back. Scripts that import `laya` need the environment `run.sh` made:
   `. .venv-finetune/bin/activate`.
5. **Copy the results down**, then **terminate** the instance (a stopped one still pays for its disk and may not
   get a GPU back):

   ```bash
   scp -i key.pem -r ubuntu@<host>:~/agentic-policy/finetune/out/tuned finetune/out/
   scp -i key.pem -r ubuntu@<host>:~/agentic-policy/finetune/results finetune/
   ```

Then load the checkpoint into the cluster: see [Fine-tuning](fine-tuning.md#3-use-the-result).

---

← Previous: [Fine-tuning the decision model](fine-tuning.md) · Next: [Results](results.md)
