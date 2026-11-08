---
title: "RStudio Server"
---

## RStudio Server

![RStudio](https://img.shields.io/badge/RStudio-75AADB?logo=rstudioide&logoColor=white)

**Browser IDE for R**

R in the browser: console, editor, plots, environment and package manager, from the [Rocker project](https://rocker-project.org)'s build of RStudio Server.

| Setting | Value |
|---------|-------|
| Default Port | `8787` (bound to `127.0.0.1` on the host) |
| Suggested Subdomain | `rstudio` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | `nexus-rstudio`, password generated per deployment (Infisical folder `rstudio`) |
| Persistence | Docker volume `rstudio-home` |
| Website | [posit.co](https://posit.co/products/open-source/rstudio-server/) |

### RStudio next to the Python IDEs

[code-server](code-server.md), [Jupyter](jupyter.md) and [marimo](marimo.md) are the Python side. RStudio is the IDE for courses taught in R, and [Shiny](shiny.md) is where its apps can be deployed.

### Login

Sign in as `nexus-rstudio` with `RSTUDIO_PASSWORD` from Infisical. Rocker's image ships a user called `rstudio`; a small init script in the stack (`00_nexus_user`) renames it before Rocker sets the password.

### First steps

```r
install.packages("palmerpenguins")
library(palmerpenguins)
summary(penguins)
plot(penguins$flipper_length_mm, penguins$body_mass_g)
```

Packages installed this way go into the user library in the home directory.

### Persistence

The home directory, with projects and installed packages, is in `rstudio-home`.

- **`rebuild` (default): it does not survive a teardown.** RStudio is not in the R2 backup list. Keep projects in a Git repository ([Forgejo](forgejo.md)).
- **`snapshot`: it survives**, because the whole disk is imaged.
