# Goblin CLI

A proof of concept Goblin CLI for goblin.run. It's currently written in python with no dependencies, but
it could be ported over to another language like Go if there's motivation.

**Requirements:** Python >3.9, I think

## Direnv integration

```
PATH_add .bin

if ! python scripts/goblin.py --check --no-fetch >/dev/null 2>&1; then
  echo ".bin directory is out of date. Run 'python goblin.py' to update." >&2
fi
```

## Sample `.goblin` file

```
PREFIX=.bin

https://goblin.run/github.com/sqlc-dev/sqlc@1.27.0
https://goblin.run/github.com/air-verse/air@1.52.3
https://goblin.run/github.com/golangci/golangci-lint/cmd/golangci-lint@c2e095c022a97360f7fff5d49fbc11f273be929a
```

## Sample generated `.goblin.lock` file

```
github.com/air-verse/air 1.52.3 1.52.3
github.com/golangci/golangci-lint/cmd/golangci-lint c2e095c022a97360f7fff5d49fbc11f273be929a c2e095c022a97360f7fff5d49fbc11f273be929a
github.com/sqlc-dev/sqlc 1.27.0 1.27.0
```

## Sample Output

```
PREFIX=.bin
[sqlc-dev/sqlc           ] Using provided version: github.com/sqlc-dev/sqlc@1.27.0
[sqlc-dev/sqlc           ] Installing https://goblin.run/github.com/sqlc-dev/sqlc@1.27.0 (1.27.0) to .bin/sqlc

  >> Downloading github.com/sqlc-dev/sqlc@1.27.0
  >> Building binary for darwin arm64 ... Please wait
  >> Installing sqlc to /somewhere/on/my/computer/goblin-cli/.bin
  >> Installation complete

Thank you for using goblin, if you like the ease of installation and would like to support the developer, please do so on http://github.com/sponsors/barelyhuman

[air-verse/air           ] Using provided version: github.com/air-verse/air@1.52.3
[air-verse/air           ] Installing https://goblin.run/github.com/air-verse/air@1.52.3 (1.52.3) to .bin/air

  >> Downloading github.com/air-verse/air@1.52.3
  >> Building binary for darwin arm64 ... Please wait
  >> Installing air to /somewhere/on/my/computer/goblin-cli/.bin
  >> Installation complete

Thank you for using goblin, if you like the ease of installation and would like to support the developer, please do so on http://github.com/sponsors/barelyhuman

[golangci/golangci-lint  ] Using provided version: github.com/golangci/golangci-lint/cmd/golangci-lint@c2e095c022a97360f7fff5d49fbc11f273be929a
[golangci/golangci-lint  ] Installing https://goblin.run/github.com/golangci/golangci-lint/cmd/golangci-lint@c2e095c022a97360f7fff5d49fbc11f273be929a (c2e095c022a97360f7fff5d49fbc11f273be929a) to .bin/golangci-lint

  >> Downloading github.com/golangci/golangci-lint/cmd/golangci-lint@c2e095c022a97360f7fff5d49fbc11f273be929a
  >> Building binary for darwin arm64 ... Please wait
  >> Installing golangci-lint to /somewhere/on/my/computer/goblin-cli/.bin
  >> Installation complete

Thank you for using goblin, if you like the ease of installation and would like to support the developer, please do so on http://github.com/sponsors/barelyhuman

Writing lock file /somewhere/on/my/computer/goblin-cli/.goblin.lock
```
