# Local Harness Acceptance Controller

This is the separate, interactive controller path for real Delivery Harness acceptance. It is not part of the GitHub provider + asset smoke because a workflow dispatch cannot substitute for explicit human approval of exact artifacts.

## Preconditions

- Use a freshly installed 0.7.0 candidate in a new Codex task and prove the plugin's 15 provider tools plus two namespaced local tools are exposed.
- Use the already approved temporary Stitch project scope or create one unique project with a cleanup plan.
- Install/check the isolated Harness runtime without putting credentials in argv:

```bash
python scripts/setup_harness_runtime.py check
```

## Interactive path

1. Create a real non-overwriting page specification:

```bash
python scripts/stitch_harness.py spec init --project /absolute/business-project --page-id live-canary
```

2. Start the run and follow each returned `next_action`. Stitch generation, ImageGen, OCR/business, roundtrip, editability and visual comparison must each produce their real typed evidence file beneath the run. Resume only with the evidence requested by the current state:

```bash
python scripts/stitch_harness.py start --project /absolute/business-project --spec live-canary
python scripts/stitch_harness.py resume --project /absolute/business-project --run RUN_ID --evidence /absolute/run/evidence/STEP.json
python scripts/setup_harness_runtime.py run compare --project /absolute/business-project --run RUN_ID
```

3. At `AWAITING_USER_APPROVAL`, show the exact accepted HTML/render/comparison artifact hashes to the user. Create the confirmation only from an explicit human approval made at that point; never derive approval from workflow dispatch, model scoring, or provider success. Then submit it:

```bash
python scripts/stitch_harness.py approve --project /absolute/business-project --run RUN_ID --confirmation /absolute/private/approval.json
```

4. Archive only after the state is `APPROVED`; verify the returned archive and then perform the separately authorized remote project cleanup:

```bash
python scripts/stitch_harness.py archive --project /absolute/business-project --run RUN_ID
python scripts/stitch_harness.py status --project /absolute/business-project --run RUN_ID
```

The controller's private record must retain the candidate SHA, installed source equality, run ID, receipt-chain verification, exact approval artifact set, archive hash and cleanup proof. Public release notes may contain only sanitized booleans, counts, hashes and timestamps.
