# Fair-play policy

The participant bundle in `data/` is read-only input. Team-created output may be written only outside `data/` (normally to `backend/derived/` or `dev_labels/`).

## Organizer answer keys

Do not open, copy, commit, or use `ground_truth.json`, data-generator scripts, or any equivalent answer-key material for development, prompts, tests, evaluation, or tuning. If an organizer-provided Docker or archive bundle exposes these files, stop inspecting that bundle and notify the organizers immediately. Use the organizer service only through `POST /submit` when evaluation begins.

The current checkout has no answer-key files or organizer communication channel. The project owner has approved continuing without an organizer notice. This deferral does not change the policy: send the notice below if a channel becomes available or an organizer bundle exposes answer-key material.

Suggested organizer notice:

> The provided organizer bundle appears to include answer-key material (`data_v2/ground_truth.json`) and generation scripts. Our team will not access or use them; please provide a participant-safe bundle or confirm the intended access boundary.

## Gemini capacity check

The team selected the Gemini 3.5 Flash-Lite free plan. The confirmed account quotas are **15 RPM**, **250,000 input TPM**, and **1,500 RPD**. The Phase 5 client must enforce the conservative caps in `.env.example`: 12 RPM, 200,000 TPM, and 1,200 RPD. Cache requests by content hash, queue excess work, and stop further requests when the daily cap is reached.

Reference: https://ai.google.dev/gemini-api/docs/rate-limits
