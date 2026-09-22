% al2dbml-validate 1

## NAME
al2dbml-validate - parse-check a DBML file

## SYNOPSIS
**al2dbml-validate** *file*

## DESCRIPTION
**al2dbml-validate** parses *file* with pydbml and exits non-zero if the
document does not parse, printing the parser error to stderr. Useful as a
smoke test in CI after generating a schema with **al2dbml**(1).

pydbml's parser is not byte-identical to dbdiagram.io's. For an
authoritative check matching dbdiagram exactly, use **dbml2sql** *file*
**--postgres** from the **@dbml/cli** npm package.

## EXAMPLES

```
al2dbml MyApp.app -o schema.dbml
al2dbml-validate schema.dbml
```

## SEE ALSO
**al2dbml**(1)
