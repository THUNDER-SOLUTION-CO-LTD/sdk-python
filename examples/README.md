# Examples

Verify a payment before crediting an order: start with the [payment checks in the main guide](../README.md#quick-start). Each script here runs one operation and prints its result. Use `--help` to see the required arguments.

Set `THUNDER_API_KEY_FILE` to a private file containing your service key. Run an account-info request:

```sh
python examples/get_info.py --run
```

For a slip, put its QR payload in the `payload` field of `input.json`, then run:

```sh
python examples/verify_bank_by_payload.py --input input.json --run
```

Inputs use `image` for a local image path, `image_url` for a public image URL, `account_id` for a receiving account and `job_id` for a submitted job. Background submissions accept `callback_url`. The API key belongs in the environment or a key file, never in input JSON.

`--run` confirms that you intend to send the request. Verification can consume quota, and account examples can change your receiving accounts. Output can contain personal data; keep it private. For a receipt you plan to accept as payment, enable receiving-account, amount and duplicate checks as shown in the main guide.
