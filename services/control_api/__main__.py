"""Document the local facade entrypoint without starting a server in tests."""

from .service import LocalControlService


def main() -> None:
    raise SystemExit("LocalControlService is an in-process facade; embed it in a local API server")


if __name__ == "__main__":
    main()

