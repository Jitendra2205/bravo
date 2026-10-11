# Evaluation

Two scripts, standard-library Python only (faster-whisper only for local speech tests).

## Task evaluation: local vs cloud

1. Edit `tasks.json` until it holds 25–30 tasks you really do. Each task has automatic `checks`.
2. Local run (Ollama must be running): `python eval/run_eval.py --target local`
3. Cloud run, any OpenAI-compatible endpoint:

   ```bash
   export CLOUD_BASE_URL=...  CLOUD_API_KEY=...  CLOUD_MODEL=...
   export CLOUD_PRICE_IN=...  CLOUD_PRICE_OUT=...   # USD per 1M tokens, from the provider's pricing page
   python eval/run_eval.py --target cloud
   ```

Results land in `results/` as CSV, with a summary table printed for the README.
Never commit a key; set it in the shell for the run only.

## Speech-to-text evaluation

1. Record 15 English and 15 Hinglish clips (WAV) into `voice/`, and list each in `voice/manifest.csv`
   with exactly what you said. Ask anyone else you record for permission; audio is git-ignored by default.
2. Local Whisper: `pip install faster-whisper`, then `python eval/stt_eval.py --whisper small,medium`
3. Compare another tool (e.g. Wispr Flow): dictate the same sentences, save a CSV with columns
   `file,hypothesis` named after the tool (`wispr-flow.csv`), then `python eval/stt_eval.py --hyp-csv wispr-flow.csv`

## Tests

`python -m unittest discover eval` — runs the checks, WER and an end-to-end run against a fake model server.
