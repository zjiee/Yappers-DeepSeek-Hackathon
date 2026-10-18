# Results

Referee output lands here, one JSON file per run:

```
results/<team>__<run_id>.json
```

The files are ignored by git so practice runs do not end up in your commits.

**Except `results/submitted/`.** The runs you recorded on your own machine are
a required part of your submission: copy the result files for the runs you want
us to see into `results/submitted/` and commit them. That directory is tracked;
everything else here stays ignored.

```sh
mkdir -p results/submitted
cp results/<your_team>__*.json results/submitted/
```

Nothing in `results/submitted/` is scored — see
[docs/07-submission.md](../docs/07-submission.md) for what it is for.

```sh
# What your last few runs did
./scripts/leaderboard.py summarise results/

# The leaderboard across every team
./scripts/leaderboard.py rank results/ --csv leaderboard.csv
```

The format is documented in [docs/05-evaluation.md](../docs/05-evaluation.md).
