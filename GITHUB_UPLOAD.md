# Publish DriveFort AI to GitHub

## Recommended repository settings

- Repository name: `DriveFort-AI`
- Description: `EV cybersecurity and digital-twin research platform with CARLA simulation, explainable threat detection, recovery, and forensic reporting.`
- Visibility: Private while the graduation project is under review; Public after checking university rules and team approval.
- Do not initialize the GitHub repository with a README, `.gitignore`, or license because these files already exist locally.

## Windows PowerShell

1. Create an empty repository on GitHub.
2. Open PowerShell inside this project folder.
3. Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\publish_github.ps1 -RepositoryUrl "https://github.com/YOUR_USERNAME/DriveFort-AI.git"
```

Git Credential Manager will ask you to sign in when necessary.

## Linux or macOS

```bash
chmod +x scripts/publish_github.sh
./scripts/publish_github.sh "https://github.com/YOUR_USERNAME/DriveFort-AI.git"
```

## Manual commands

```bash
git init -b main
git add .
git commit -m "Initial release: DriveFort AI V3"
git remote add origin https://github.com/YOUR_USERNAME/DriveFort-AI.git
git push -u origin main
```

GitHub no longer accepts an account password for Git operations over HTTPS. Use the browser sign-in flow provided by Git Credential Manager or a personal access token when prompted.
