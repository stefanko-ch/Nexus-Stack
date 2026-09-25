# =============================================================================
# Shiny Server - R web applications
# =============================================================================
# Base: rocker/shiny, the Rocker project's image, which is what upstream
# points at — RStudio/Posit publish no maintained Shiny Server image of
# their own any more.
#
# amd64 only. Checked against Docker Hub: every rocker/shiny tag lists a
# single architecture. That is fine here, because Nexus-Stack runs on x86
# (cx43), but it does mean this stack will not build on an Apple Silicon
# laptop without `--platform linux/amd64`.
#
# Two things are added:
#
#   git         the entrypoint clones the Forgejo workspace repository,
#               and the base image has no git at all (checked)
#   R packages  a Shiny app that can only draw plain text is not much of
#               a demonstration; these are what an app here reaches for
#
# What is deliberately NOT added: curl and wget. The base image has
# neither, and the healthcheck uses python3, which it does have.
# =============================================================================

FROM rocker/shiny:4.6.1

RUN apt-get update && \
    apt-get install -y --no-install-recommends git libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# A dated Posit Package Manager snapshot rather than the image's own
# `latest`. p3m serves Ubuntu binaries for this exact release, so the
# install is a download rather than a compile — and the date pins what
# gets downloaded, so a rebuild six months from now installs the same
# versions this was tested against.
RUN Rscript -e "options(repos = c(CRAN = 'https://p3m.dev/cran/__linux__/noble/2026-09-01')); \
      install.packages(c('DBI', 'RPostgres', 'ggplot2', 'dplyr', 'DT'), Ncpus = 4)" && \
    Rscript -e "stopifnot(all(c('DBI','RPostgres','ggplot2','dplyr','DT') %in% rownames(installed.packages())))"

EXPOSE 3838
