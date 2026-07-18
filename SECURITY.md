# Security Policy

DriveFort AI is an academic cyber-physical security demonstration. It is not certified for public-road use and must not control a real vehicle.

## Reporting a vulnerability

Do not publish secrets, personal data, or exploitable details in a public issue. Contact the repository owner privately through the contact method listed on their GitHub profile and include:

- A clear description of the issue.
- Steps to reproduce it in the simulator or mock environment.
- The affected version and environment.
- A suggested mitigation, when available.

## Secure configuration

- Never commit `.env` files, tokens, private keys, or CARLA machine credentials.
- Set `DRIVEFORT_COMMAND_SECRET` and `DRIVEFORT_OTA_SECRET` to independent long random values.
- Keep `DRIVEFORT_OTA_DEMO_SIGNING=0` outside controlled demonstrations.
- Keep `DRIVEFORT_ALLOW_MOCK=0` when making claims about live CARLA behavior.
- Do not expose the Flask development server directly to an untrusted network.
