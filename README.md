# plumbingbird
Handy tools for common use cases in data engineering

## Purpose

I got tired of reinventing wheels across jobs in data engineering, so I decided to make a repo for them instead. Nothing in here is specific business logic, it's intended to be mostly higher order functions so you can plug and play.

### Installation Dependencies
1. `[postgresql](https://www.postgresql.org/download/)`
2. `[poetry](https://python-poetry.org/docs/#installation)`

## Organization

### Utilities

This directory contains primitive parent classes for concepts in both orchestration and etl, as well as a number of handy tools for environment interaction (like ID-ing where something is running and getting secrets out of the env vars). Someday, maybe the etl and orchestration classes will move to their respective directories, but for now they're just chilling in the base utilities directory.

### ETL

This directory contains classes for extraction, transformation, and loading, differentiated by the nature of the source (in the case of extraction), the nature of the destination (in the case of loaders), and the format of the interstitial data (for transformers/buffers).

### Orchestration

This directory has provider-bounded tools for standing up cloud services, like Workers that can listen to queues and Jobs they can do.

### Tests

What's on the tin, plus some differentiation therein between live tests that take action vs unittests.