"""Container entrypoint: validate deployment settings, then run one SQLite worker."""
import os
import sys


def command(env):
    secret = env.get('SECRET_KEY', '')
    if len(secret) < 32 or secret in ('dev-secret', 'change-me'):
        raise ValueError('Set a stable random SECRET_KEY with at least 32 characters.')
    port = env.get('PORT', '8000')
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError('PORT must be between 1 and 65535.')
    return [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0',
            '--port', port, '--workers', '1', '--proxy-headers', '--no-access-log']


def main():
    try:
        args = command(os.environ)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    # Never print credentials or log OAuth callback authorization codes.
    os.execv(args[0], args)


if __name__ == '__main__':
    main()
