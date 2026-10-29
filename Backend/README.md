# Backend & Build Service

## Run from Source

```powershell
python Frontend\desktop_app.py
```

## Build Standalone EXE

The build process uses PyInstaller with `--onefile` and `--windowed`:

```powershell
python Backend\build_desktop_exe.py
```

Output binary:
```text
Backend\dist\Тестировщик.exe
```

## Default Admin Credentials

On initial database setup, a default administrator is automatically created:

```text
Username: admin
Password: admin
```

Credentials can also be customized via environment variables prior to initial launch:
```powershell
$env:TESTER_ADMIN_USER="my_admin"
$env:TESTER_ADMIN_PASSWORD="strong_password"
```
