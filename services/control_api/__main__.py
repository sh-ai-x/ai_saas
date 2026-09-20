"""Run the local control API."""


def main() -> None:
    from .http import serve

    serve()


if __name__ == "__main__":
    main()
