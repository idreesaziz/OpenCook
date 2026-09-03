# Benchmarks

The benchmark command executes planners against the bundled fixture and reports measured route count, node expansions, and wall time. Run it on the target machine; committed prose does not contain fabricated timing numbers.

```bash
uv run opencook benchmark --iterations 100 --json
```

Fixture timing is a regression microbenchmark, not evidence of full-corpus performance. Corpus benchmarks should additionally report solved-target percentage, route recovery, reaction expansions, memory peak, route length, and disconnection diversity, with dataset and stock versions fixed.

