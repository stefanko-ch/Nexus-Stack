# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.4.0...v0.5.0) (2026-01-18)


### 🚀 Features

* **scripts:** Auto-sync missing secrets to Infisical on re-deployments ([9d60dc0](https://github.com/stefanko-ch/Nexus-Stack/commit/9d60dc0ae2cb4ad45bec889f12021104f40c7f1a))
* **stacks:** Add MinIO + Infisical auto-sync + Grafana fixes ([546d4c4](https://github.com/stefanko-ch/Nexus-Stack/commit/546d4c4358e30079c750e5396552ab05ee7cb5ff))
* **stacks:** Add MinIO S3-compatible object storage ([54a4140](https://github.com/stefanko-ch/Nexus-Stack/commit/54a414038d3b979289245e7a57b205316b4d0465))


### 🐛 Bug Fixes

* add working directory to Uptime Kuma setup scripts ([962ca04](https://github.com/stefanko-ch/Nexus-Stack/commit/962ca04209fcd9a3045c40671be401190edc2e7a))
* **grafana:** Correct Prometheus and cAdvisor Docker image tags ([84ef522](https://github.com/stefanko-ch/Nexus-Stack/commit/84ef522edaa9f75eaa2012a5ba9c26f153fb7048))
* **grafana:** Use exact versions instead of 'latest' tags ([5c6b108](https://github.com/stefanko-ch/Nexus-Stack/commit/5c6b1086362bad06d0a782b5b7f7d0cc667f66d3))
* improve Infisical warning comment per review feedback ([365b503](https://github.com/stefanko-ch/Nexus-Stack/commit/365b5037cf91147166424179f13354e27d929df6))
* resolve deployment issues from PR [#141](https://github.com/stefanko-ch/Nexus-Stack/issues/141) ([d573557](https://github.com/stefanko-ch/Nexus-Stack/commit/d573557909179c5c1a546c034b5e85fff46bd971))
* Revert broken Infisical auto-sync and fix cAdvisor image tag ([1af45d0](https://github.com/stefanko-ch/Nexus-Stack/commit/1af45d068bb160b69089a44486c7446aa22713e9))


### ♻️ Refactoring

* **scripts:** Optimize Metabase health check with fast-path ([a33fc55](https://github.com/stefanko-ch/Nexus-Stack/commit/a33fc559ebac16c94cc3109b83625fe72c4eb629))


### 📚 Documentation

* **stacks:** Clarify MinIO S3 API access is localhost-only ([d680157](https://github.com/stefanko-ch/Nexus-Stack/commit/d680157a0b71ed866f534e718bcda85f40872f2e))

## [0.4.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.3.0...v0.4.0) (2026-01-18)


### 🚀 Features

* **stacks:** Add Mage AI data pipeline platform ([9f2b6ee](https://github.com/stefanko-ch/Nexus-Stack/commit/9f2b6ee3df0dfe44b7b6cfd86f38e92b15f4a8b1))
* **stacks:** Add Mage AI data pipeline stack ([2711723](https://github.com/stefanko-ch/Nexus-Stack/commit/271172391fff2886f781a0e82bdfdbcbefbddb5e))


### 🐛 Bug Fixes

* Address PR review comments ([82614e3](https://github.com/stefanko-ch/Nexus-Stack/commit/82614e31a31f8238f7803d95f5c0ec7ab8cb3144))
* **control-plane:** Add debug logging to info API ([8215739](https://github.com/stefanko-ch/Nexus-Stack/commit/821573947cd25618d5c8f6e5f29bad69474032e9))
* **control-plane:** Add debug logging to info API and fetchInfo ([08e7b5a](https://github.com/stefanko-ch/Nexus-Stack/commit/08e7b5accba5915a642358b390ed9e3e1c52cd97))
* **stacks:** Add port mapping to Mage container ([6de6944](https://github.com/stefanko-ch/Nexus-Stack/commit/6de6944b5cb221f750171374ee90ae42020fce53))
* Use consistent ternary operators for env variable checks ([b7c44b1](https://github.com/stefanko-ch/Nexus-Stack/commit/b7c44b1958375f232ed98d34844d59ff683124b2))


### 📚 Documentation

* Add active development note to disclaimer ([1709365](https://github.com/stefanko-ch/Nexus-Stack/commit/17093654517717a123cefa875079867138c5486b))
* Add branch cleanup rules to prevent deleting release-please branch ([92468ef](https://github.com/stefanko-ch/Nexus-Stack/commit/92468ef1b1ce297e31bedff420a1cccd345dc037))
* Add Mage AI to stacks.md and config.tfvars.example ([30aac20](https://github.com/stefanko-ch/Nexus-Stack/commit/30aac207155890c134e59760295aa30dc738fdf4))
* **agents:** Add branch cleanup rules ([8a4cf1d](https://github.com/stefanko-ch/Nexus-Stack/commit/8a4cf1d6d2c12bf4f68bf6ae230ede1ea390691f))
* **agents:** Add branch cleanup rules ([4704635](https://github.com/stefanko-ch/Nexus-Stack/commit/47046350b42de8aab7b63ed7d23bd89c7c67ccfe))


### 🔧 Maintenance

* Add debug logging for info panel troubleshooting ([92c8dde](https://github.com/stefanko-ch/Nexus-Stack/commit/92c8dde0088046943728dd41d9d569a74423f1ff))
* Enable all services for testing ([705c6d3](https://github.com/stefanko-ch/Nexus-Stack/commit/705c6d3bd0423ec7cbea4ae319c3c9ea83de5e13))

## [0.3.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.2.0...v0.3.0) (2026-01-18)


### 🚀 Features

* Add IPv6-only support and dynamic R2 bucket naming ([70b70c1](https://github.com/stefanko-ch/Nexus-Stack/commit/70b70c1a79a423787db705c4248075f2e2835ad3))
* Add IPv6-only support and dynamic R2 bucket naming ([ccf3a07](https://github.com/stefanko-ch/Nexus-Stack/commit/ccf3a078bd5c3c1f9d83388c580f690ca258afb2)), closes [#112](https://github.com/stefanko-ch/Nexus-Stack/issues/112)
* Add multi-tenant naming and user account support ([242a4c9](https://github.com/stefanko-ch/Nexus-Stack/commit/242a4c9118793b1b21da2b28aeda75537814bfa3))
* Add multi-tenant naming with domain-based resource prefix ([4998b46](https://github.com/stefanko-ch/Nexus-Stack/commit/4998b462f2af9fa2d4895ecf21b195e42f8e524b))
* Move user emails to services.tfvars for automatic configuration ([dbadbad](https://github.com/stefanko-ch/Nexus-Stack/commit/dbadbad8582deb47093f28ec90e98a33dc561b09))
* Send notifications to both admin and user ([7d0bdcb](https://github.com/stefanko-ch/Nexus-Stack/commit/7d0bdcb73f2bdd7bdcafcea6989eb8cc64569dfe))
* Set ipv6_only default to true ([4c5f202](https://github.com/stefanko-ch/Nexus-Stack/commit/4c5f20242081084728a3b764fc8fe110f897cf54))
* **stacks:** Add CloudBeaver auto-setup with admin credentials ([481ee67](https://github.com/stefanko-ch/Nexus-Stack/commit/481ee67dc06605a4fc643e281d63aeb756909cdc))
* **stacks:** Add CloudBeaver database management tool ([c28912a](https://github.com/stefanko-ch/Nexus-Stack/commit/c28912ac770cbd017272d479dc83db6c39dd9236))
* **stacks:** Add CloudBeaver database management tool ([07e1e3f](https://github.com/stefanko-ch/Nexus-Stack/commit/07e1e3f57f73701da974338c8cd2caa4dfd93b2f)), closes [#44](https://github.com/stefanko-ch/Nexus-Stack/issues/44)


### 🐛 Bug Fixes

* Add environment variables to Worker for email notifications ([ed88fd3](https://github.com/stefanko-ch/Nexus-Stack/commit/ed88fd3cd23bc6c4697011f8473cb7f2907c2267))
* Add fetchInfo() to populate Infrastructure Information panel ([53799e0](https://github.com/stefanko-ch/Nexus-Stack/commit/53799e0d36285c5d275469fbd53a6d82cdaaa930))
* Add SERVER_TYPE and SERVER_LOCATION to Pages secrets ([c3a6eca](https://github.com/stefanko-ch/Nexus-Stack/commit/c3a6ecaf6144e60c7837ccd51cf6761333cdfbf1))
* Add USER_EMAIL to Pages secrets for credential emails ([eb87808](https://github.com/stefanko-ch/Nexus-Stack/commit/eb87808b24e976b0ca860d5b9b33af60cbf09b8d))
* Control Plane secrets and info panel ([30c8dc1](https://github.com/stefanko-ch/Nexus-Stack/commit/30c8dc169297b79c625ade0fe16f64a97f74e295))
* Correct cax31 server specifications in comments ([9a3acf1](https://github.com/stefanko-ch/Nexus-Stack/commit/9a3acf1cad0f7afb56f21839a7dd640886d6aafd))
* Disable IPv6-only mode due to connectivity issues ([#129](https://github.com/stefanko-ch/Nexus-Stack/issues/129)) ([a9564e8](https://github.com/stefanko-ch/Nexus-Stack/commit/a9564e8779a881cc0bbf1e76f96077211113ca58))
* Make TF_VAR_domain required, remove fallback bucket name ([3e268f5](https://github.com/stefanko-ch/Nexus-Stack/commit/3e268f5dc616db9ae3501d52cde89df5c803a4ab))
* **redpanda-console:** Remove invalid cross-stack depends_on ([edc2740](https://github.com/stefanko-ch/Nexus-Stack/commit/edc274098cdab08c5bdc86625e2c6d6960a17351))
* **redpanda-console:** Remove invalid cross-stack depends_on ([1a5366f](https://github.com/stefanko-ch/Nexus-Stack/commit/1a5366fda064e408cad67da27d1e020dcfa19d20))
* Remove API response printing from init-r2-state.sh ([0a6ead7](https://github.com/stefanko-ch/Nexus-Stack/commit/0a6ead7ac07267eb8473ca6ccaf5777f54c1eb7f))
* Remove duplicate admin_email/user_email from generated config ([b28fde9](https://github.com/stefanko-ch/Nexus-Stack/commit/b28fde9d793875336091cba5b56a995842c2f959))
* Remove password printing from deploy logs ([9a47b1c](https://github.com/stefanko-ch/Nexus-Stack/commit/9a47b1c52598ffd57a991eb78c11a189ced3d2f3))
* Send emails to user with admin in CC ([db1e3e3](https://github.com/stefanko-ch/Nexus-Stack/commit/db1e3e322b6013f173bdb3320020041134555721))
* Send emails to user with admin in CC ([faab4af](https://github.com/stefanko-ch/Nexus-Stack/commit/faab4af300bde3b51ab8c5de263f273737651329))
* Send stack online email to both admin and user ([ef8989a](https://github.com/stefanko-ch/Nexus-Stack/commit/ef8989ae35b6d0702cd58e03052c25f770c286b9))
* Use awk instead of sed for email extraction in workflows ([4154496](https://github.com/stefanko-ch/Nexus-Stack/commit/4154496f215cf5dc9a8b235244ba7e0436de5ff3))
* Use bash code fence and add concrete example ([695e030](https://github.com/stefanko-ch/Nexus-Stack/commit/695e0303592a53efdf70cfd05dc1b2916ba25c1d))
* Use TF_VAR_admin_email for Control Plane secrets ([aa71251](https://github.com/stefanko-ch/Nexus-Stack/commit/aa71251c10d1efbb4ff2444ba8af900d5bb5efde))
* Use TF_VAR_admin_email for spin-up email notification ([5eccd65](https://github.com/stefanko-ch/Nexus-Stack/commit/5eccd650d0d61706a30266ae7043e6ceb03c3725))
* Use TF_VAR_admin_email for spin-up email notification ([59d639b](https://github.com/stefanko-ch/Nexus-Stack/commit/59d639bb337b772790d557e887704a0d267431dd))


### ♻️ Refactoring

* Move email configuration from services.tfvars to GitHub Secrets ([49e8d38](https://github.com/stefanko-ch/Nexus-Stack/commit/49e8d386d594c018d223c72b93403b4c0ae65321))
* Simplify ipv4_enabled to use negation directly ([b887af1](https://github.com/stefanko-ch/Nexus-Stack/commit/b887af1de5c0157901c51156d367426ebb06210b))


### 📚 Documentation

* Add critical security rule - never print secrets to logs ([f32b5c2](https://github.com/stefanko-ch/Nexus-Stack/commit/f32b5c2b7e9a50add240b75636e884290425d03f))
* Add info and debug API endpoints documentation ([f4caea7](https://github.com/stefanko-ch/Nexus-Stack/commit/f4caea71fcaa6a26fd8e0d1150d1a23a92a35184))
* **agents:** Fix PR/issue creation - use create_file instead of heredoc ([3d269f1](https://github.com/stefanko-ch/Nexus-Stack/commit/3d269f1e152668ae52400573948613b5d3eefc12))
* **agents:** Fix PR/issue creation instructions ([b6c8c02](https://github.com/stefanko-ch/Nexus-Stack/commit/b6c8c027a782d7dd82d5ba571f6067d6f5f2abda))


### 🔧 Maintenance

* Enable Redpanda and CloudBeaver for testing ([28019f8](https://github.com/stefanko-ch/Nexus-Stack/commit/28019f88aec203e6934146fe93209093b4839aa2))

## [0.2.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.1.0...v0.2.0) (2026-01-16)


### ⚠ BREAKING CHANGES

* **ci:** Simplified environment variable management

### 🚀 Features

* Add automated SSH key management with Infisical storage ([e0ea65e](https://github.com/stefanko-ch/Nexus-Stack/commit/e0ea65ef909211c62b1b19cf5d154bedd7183037))
* Add Metabase auto-setup in deploy.sh ([74dc8a9](https://github.com/stefanko-ch/Nexus-Stack/commit/74dc8a9acc19e2662bebf1286342a639b7d90031))
* Add optional Docker Hub login for increased pull rate limits ([565fcdf](https://github.com/stefanko-ch/Nexus-Stack/commit/565fcdf1f888aa1504cce1d1f84d35d04bc74c70))
* Add optional scheduled teardown via Cloudflare Worker ([11a39ac](https://github.com/stefanko-ch/Nexus-Stack/commit/11a39ac06bdde4efcdb8e2ba379fe3d39e120371))
* Add Resend email for credentials and Mailpit stack ([281d5e3](https://github.com/stefanko-ch/Nexus-Stack/commit/281d5e362bcd09c115c1448e6178270186e9feee))
* Add Resend email notifications and Mailpit stack ([8379872](https://github.com/stefanko-ch/Nexus-Stack/commit/837987225a26300df5514635fdb2e6b9cd263b37))
* Add scheduled daily teardown with email notification ([024d23b](https://github.com/stefanko-ch/Nexus-Stack/commit/024d23bcd846653df90e2f5d31ed264f08c9e711))
* Automated SSH key management and Control Plane fixes ([8c74112](https://github.com/stefanko-ch/Nexus-Stack/commit/8c74112250d164766c9bd67522de79698f399df5))
* **ci:** Add Docker Hub credentials support to GitHub Actions ([581f253](https://github.com/stefanko-ch/Nexus-Stack/commit/581f25368dd61ded57c3d9bcfb956d39e086b806))
* **ci:** Add manual deployment workflows ([8371d8d](https://github.com/stefanko-ch/Nexus-Stack/commit/8371d8d55b9a96c7a2dd29c2815416572373d819))
* **ci:** Add manual deployment workflows ([92592cd](https://github.com/stefanko-ch/Nexus-Stack/commit/92592cd2428605fec4fbc0938225ae926d8f909b))
* **ci:** auto-save Infisical admin password to GitHub Secrets ([df701f7](https://github.com/stefanko-ch/Nexus-Stack/commit/df701f79790b2441b152909860e21c453285c639))
* **ci:** Auto-save Infisical admin password to GitHub Secrets ([e3134e4](https://github.com/stefanko-ch/Nexus-Stack/commit/e3134e4708118f8f35cc9a68948e9c2350a906e2))
* **control-panel:** Add debug endpoint for environment variables ([e0f735f](https://github.com/stefanko-ch/Nexus-Stack/commit/e0f735fa96a7edd4d624ffb81f5f26da5507fb25))
* **control-panel:** Add infrastructure information panel ([d60aac7](https://github.com/stefanko-ch/Nexus-Stack/commit/d60aac700c47e212d4bee444594b2244f5538e6b))
* **control-panel:** Add service toggles and separate setup/spin-up workflows ([0685880](https://github.com/stefanko-ch/Nexus-Stack/commit/06858802302fe83b2a2dfb893ad6557d4beca161))
* **control-panel:** Add service toggles and separate setup/spin-up workflows ([c02e10f](https://github.com/stefanko-ch/Nexus-Stack/commit/c02e10f9ad6cb28f984d508aa4a2e469d93c8158))
* **control-panel:** Add web-based infrastructure control panel ([dffb59b](https://github.com/stefanko-ch/Nexus-Stack/commit/dffb59b450967eb67a0fcec851a59cbe2c98dc9c))
* **control-panel:** Add web-based infrastructure control panel ([63bd6b9](https://github.com/stefanko-ch/Nexus-Stack/commit/63bd6b9619459f6b4b5b8fd7adbdf4ed81162060))
* **control-panel:** Remove Destroy button and add Scheduled Teardown UI ([19feab0](https://github.com/stefanko-ch/Nexus-Stack/commit/19feab0f01da7d64c53c116941efb8d3985f4da6))
* **control-panel:** Set default scheduled teardown to enabled ([c75006a](https://github.com/stefanko-ch/Nexus-Stack/commit/c75006a8bf5107d871b0e0e5d59a369e20fdac78))
* **control-plane:** Add infrastructure info, core services, and fixes ([282325a](https://github.com/stefanko-ch/Nexus-Stack/commit/282325a3d599f71028cd8594f38df5d20d169315))
* **control-plane:** Fix KV bindings, email, and core services ([27b3b20](https://github.com/stefanko-ch/Nexus-Stack/commit/27b3b20ec76851fafb7e439dd9f1f433e793a80c))
* Pin Docker images to specific versions for stability ([554a9cd](https://github.com/stefanko-ch/Nexus-Stack/commit/554a9cdfab18d128726dfb2c472db50820d1bfbe))
* **scripts:** Add Cloudflare Pages diagnostics script ([053199c](https://github.com/stefanko-ch/Nexus-Stack/commit/053199c0dc11c924d1080f4da9b93a030decd357))
* Show Docker image versions on Info page ([4b200c6](https://github.com/stefanko-ch/Nexus-Stack/commit/4b200c65366853b3395620de6f83f442ee93531e))
* Stack improvements - Image versioning, service fixes, documentation ([702ec24](https://github.com/stefanko-ch/Nexus-Stack/commit/702ec241d71f46e35a4da88b6985a0e97aa9c31e))
* **stacks:** Add Grafana observability stack ([7b0b5e7](https://github.com/stefanko-ch/Nexus-Stack/commit/7b0b5e7e83f2ffaba4383f5c1ed0d8397685cced))
* **stacks:** Add Infisical secret management with full automation ([2b82cba](https://github.com/stefanko-ch/Nexus-Stack/commit/2b82cba14008dacbcf305886f6d57148236d2a04))
* **stacks:** Add Infisical secret management with full automation ([dd817ac](https://github.com/stefanko-ch/Nexus-Stack/commit/dd817ace083c0a321fadda65a401bbdbc8998c42)), closes [#7](https://github.com/stefanko-ch/Nexus-Stack/issues/7) [#4](https://github.com/stefanko-ch/Nexus-Stack/issues/4) [#3](https://github.com/stefanko-ch/Nexus-Stack/issues/3) [#2](https://github.com/stefanko-ch/Nexus-Stack/issues/2)
* **stacks:** Add Info dashboard with dynamic generation ([7010242](https://github.com/stefanko-ch/Nexus-Stack/commit/70102426a5289442287c1b23e443fcbfbf752560))
* **stacks:** Add Info dashboard with dynamic generation ([c03e7e5](https://github.com/stefanko-ch/Nexus-Stack/commit/c03e7e5225dbc33dc427bbe4bed3b75293cc1f1a))
* **stacks:** Add Kestra workflow orchestration platform ([675c5cf](https://github.com/stefanko-ch/Nexus-Stack/commit/675c5cfefb8ec805feb88a241e25ffd8a855811e))
* **stacks:** Add Kestra workflow orchestration platform ([1fd4f4e](https://github.com/stefanko-ch/Nexus-Stack/commit/1fd4f4ee30d7424037756d8feff1f1127615e953))
* **stacks:** Add Marimo reactive Python notebook ([caad75b](https://github.com/stefanko-ch/Nexus-Stack/commit/caad75b6838616986479fe566f2060efd4499bd4))
* **stacks:** Add Marimo reactive Python notebook ([e277484](https://github.com/stefanko-ch/Nexus-Stack/commit/e27748405cfff21c70c7a779a621528279609743))
* **stacks:** Add Metabase business intelligence tool ([4be949b](https://github.com/stefanko-ch/Nexus-Stack/commit/4be949b54837eae083deb8226b5e0ac7fcddafbd))
* **stacks:** Add Metabase business intelligence tool ([ded5dbf](https://github.com/stefanko-ch/Nexus-Stack/commit/ded5dbf7e9ca0b1d78b2ba1da457e9c32f7d6231)), closes [#47](https://github.com/stefanko-ch/Nexus-Stack/issues/47)
* **stacks:** add n8n workflow automation stack ([#20](https://github.com/stefanko-ch/Nexus-Stack/issues/20)) ([9c29304](https://github.com/stefanko-ch/Nexus-Stack/commit/9c29304b7235ce579b98f9561a0f8307d640b602))
* **stacks:** Add Portainer container management ([4ef19d8](https://github.com/stefanko-ch/Nexus-Stack/commit/4ef19d86c63fb3bc1299c052ab803808b08bbbd9))
* **stacks:** Add Portainer container management ([7e57fd3](https://github.com/stefanko-ch/Nexus-Stack/commit/7e57fd333ba4f7b01486cb89bb10eaa056ceaf14))
* **stacks:** Add Uptime Kuma monitoring stack ([40515d8](https://github.com/stefanko-ch/Nexus-Stack/commit/40515d8443c34134d8071524ede259674714d887))
* **stacks:** Add Uptime Kuma monitoring stack ([2ab5315](https://github.com/stefanko-ch/Nexus-Stack/commit/2ab53155f462342b185d0359a7556035d5d96644))
* standardize repository with community health files and badges ([4e047f9](https://github.com/stefanko-ch/Nexus-Stack/commit/4e047f9db9c546c823abfb833aa9958685e6cf38))
* **tofu:** Add multiple authentication methods support ([257d05d](https://github.com/stefanko-ch/Nexus-Stack/commit/257d05d9a06f6292a3beb4961fcb6e5d4bce666f))
* **tofu:** Add preview environment variables to Terraform ([df77ec7](https://github.com/stefanko-ch/Nexus-Stack/commit/df77ec79ad6f43af334919cbc6ae9f3150637120))
* **tofu:** Add SSH Service Token for headless authentication ([529ac61](https://github.com/stefanko-ch/Nexus-Stack/commit/529ac61ec97d5bfd0c766ed023a53019d5fda2b2))
* **tofu:** Add SSH Service Token for headless authentication ([83f2e36](https://github.com/stefanko-ch/Nexus-Stack/commit/83f2e36b3c0a63841de33badafe4da4a8814626f))
* **tofu:** Migrate state storage from local to Cloudflare R2 ([d09637a](https://github.com/stefanko-ch/Nexus-Stack/commit/d09637a3fadbcbbb35e278b103ffdd1f9a6e2899))
* **tofu:** Migrate state storage from local to Cloudflare R2 ([be17116](https://github.com/stefanko-ch/Nexus-Stack/commit/be17116eb2174e4d8c67011f8c9cdaa31a58bfc9))
* **ui:** Improve Control Plane and Info page UI ([d0add14](https://github.com/stefanko-ch/Nexus-Stack/commit/d0add14fdbe2d76c95b9be3fae5814c1289a52cf))
* **ui:** Improve Control Plane and Info page UI ([39ac0c7](https://github.com/stefanko-ch/Nexus-Stack/commit/39ac0c78007f6391e91833cff8f5bf0abf455046))


### 🐛 Bug Fixes

* Add Access Application with inline policy and CORS for API ([9d50233](https://github.com/stefanko-ch/Nexus-Stack/commit/9d502337c435e91842729465accc96bd5f43470c))
* Add cloudflare_pages_domain for custom domain, fix logo distortion, add Control to Info Page ([c710b18](https://github.com/stefanko-ch/Nexus-Stack/commit/c710b18361716e76fa73c9288d6452704e53ba2b))
* Add credentials to fetch calls for Cloudflare Access ([5f342c3](https://github.com/stefanko-ch/Nexus-Stack/commit/5f342c31080a414e61030adf1d2c8d36a160bbfc))
* Add credentials to fetch calls for Cloudflare Access ([943ea36](https://github.com/stefanko-ch/Nexus-Stack/commit/943ea36d86d1f40b9c089195b0fc8aef5e3a462b))
* Add error handling and safe JSON encoding to website dispatch ([288ee6e](https://github.com/stefanko-ch/Nexus-Stack/commit/288ee6e26aba5bb47a69e7a5bc85dfaeefc3ead6))
* Add explicit check for functions directory ([87855a4](https://github.com/stefanko-ch/Nexus-Stack/commit/87855a4506a7066ca70a4c444b258dedfa642807))
* Add Kestra to Infisical, fix n8n setup, change username to nexus ([42f9a25](https://github.com/stefanko-ch/Nexus-Stack/commit/42f9a255dcb5186e893e7a29ef895a658c1d93b5))
* Add Metabase to services.tfvars ([0bea898](https://github.com/stefanko-ch/Nexus-Stack/commit/0bea898fcd9c792895a9bced978b8da47900644e))
* Add password change reminder to credentials email ([4a3390a](https://github.com/stefanko-ch/Nexus-Stack/commit/4a3390a2ceeee59a79ec388b4bd727b7c5e685a4))
* Add PNG logo and move descriptions to services.tfvars ([e39106d](https://github.com/stefanko-ch/Nexus-Stack/commit/e39106d67f10c8246f9d7a0fd1bf13e7c93e2156))
* Add PNG logo and move descriptions to services.tfvars ([9533f3d](https://github.com/stefanko-ch/Nexus-Stack/commit/9533f3d3d33d7d45e92fa2aed83781924a088e47))
* Address additional PR review comments ([0668002](https://github.com/stefanko-ch/Nexus-Stack/commit/0668002dc345876293da7f90ea40f7550a6a10e2))
* Address Copilot review comments ([79bf352](https://github.com/stefanko-ch/Nexus-Stack/commit/79bf35249a9c558bba766ff8ec7e768b9868ee12))
* Address PR review comments ([b830d06](https://github.com/stefanko-ch/Nexus-Stack/commit/b830d06dee9c831f03a0aa602a3ac2e47bc9c77d))
* Address PR review comments ([f470735](https://github.com/stefanko-ch/Nexus-Stack/commit/f470735904bbd7ea5807cb5e98574460863abea8))
* Address PR review comments ([7f5ef69](https://github.com/stefanko-ch/Nexus-Stack/commit/7f5ef69954b1ff2a80d174a9942bc4407a9a92b7))
* Address PR review comments ([9e80a52](https://github.com/stefanko-ch/Nexus-Stack/commit/9e80a52f955441a404e51aa3311a474c3af9601d))
* Address PR review comments ([53fa498](https://github.com/stefanko-ch/Nexus-Stack/commit/53fa4987beb060566378dd808bb88ac67bc5b0ff))
* Address PR review comments ([5418aa6](https://github.com/stefanko-ch/Nexus-Stack/commit/5418aa67c16731357732de6010540ba22707b0bd))
* Address PR review comments ([8e6b837](https://github.com/stefanko-ch/Nexus-Stack/commit/8e6b8376d84aa1a634085ef6aaf33a6d45b2c873))
* Address PR review comments ([a79397b](https://github.com/stefanko-ch/Nexus-Stack/commit/a79397bf4a2e141ff4a38b7e5c7ee590631617dc))
* Address PR review comments (round 2) ([91aaf96](https://github.com/stefanko-ch/Nexus-Stack/commit/91aaf96e0daf6c75a6cc04704720f58a1fef37a4))
* Address remaining Copilot review comments ([cbd782f](https://github.com/stefanko-ch/Nexus-Stack/commit/cbd782f57512035c4d8d3684a3066a35aff1bed5))
* **ci:** Add automatic cleanup of orphaned resources before deploy ([a5e0523](https://github.com/stefanko-ch/Nexus-Stack/commit/a5e05234b3979232e4d30c7a5d73bb42183c0ed2))
* **ci:** Add deployment note and ensure production environment ([5059a2d](https://github.com/stefanko-ch/Nexus-Stack/commit/5059a2d5f48824451b94a941e91fc48a6bceb846))
* **ci:** Add DOMAIN as wrangler secret in deploy workflow ([87d70db](https://github.com/stefanko-ch/Nexus-Stack/commit/87d70db7015dc1aa27ed5a3749b0bb0b244417ff))
* **ci:** Add missing cloudflared installation to spin-up workflow ([f0b6a5b](https://github.com/stefanko-ch/Nexus-Stack/commit/f0b6a5bbe60d01f7ff8d6678ed3de789e9cebe43))
* **ci:** Add missing CNAME record target to deploy workflow ([24f98fd](https://github.com/stefanko-ch/Nexus-Stack/commit/24f98fdb32d8dd8a85d0371fa1e0f43b80522579))
* **ci:** Add pages_build_output_dir to wrangler.toml for KV bindings ([6c4d18e](https://github.com/stefanko-ch/Nexus-Stack/commit/6c4d18e5e7282d4534b911390a962b45058ac5a6))
* **ci:** Add Scheduled Teardown Worker secrets setup ([2bdf13d](https://github.com/stefanko-ch/Nexus-Stack/commit/2bdf13d4f8e5c7cd506891222405d7b68d0ce202))
* **ci:** add timestamp to R2 token name, cleanup tokens on destroy-all ([acdafc1](https://github.com/stefanko-ch/Nexus-Stack/commit/acdafc1adb0b00a6ab0403b795fb69db0072038b))
* **ci:** add timestamp to R2 token name, cleanup tokens on destroy-all ([c573fbc](https://github.com/stefanko-ch/Nexus-Stack/commit/c573fbc3bfb5f440f42d9f214e3640e6406f8f28))
* **ci:** Add Wrangler Pages deploy step for control panel ([7c12ee5](https://github.com/stefanko-ch/Nexus-Stack/commit/7c12ee515509a771740f943f5209b6836a31c6b9))
* **ci:** Add Wrangler Pages deploy step for control panel ([57b4b86](https://github.com/stefanko-ch/Nexus-Stack/commit/57b4b86f1c205c1bacc40e909028017ca09487a7))
* **ci:** Address PR review comments for validate-workflows ([e8c98c7](https://github.com/stefanko-ch/Nexus-Stack/commit/e8c98c78f3ad515721bab680398400356e362bc7))
* **ci:** Create .ssh directory before writing SSH key files ([49d112f](https://github.com/stefanko-ch/Nexus-Stack/commit/49d112ff445e7d0fe635fbfd22fd2bfefc102e6b))
* **ci:** Create .ssh directory before writing SSH key files ([22899c1](https://github.com/stefanko-ch/Nexus-Stack/commit/22899c1c0c9dae2de4208c15b06fe4725bb6c6d3))
* **ci:** delete R2 secrets on destroy-all ([22704aa](https://github.com/stefanko-ch/Nexus-Stack/commit/22704aa57b867b0ff8f5879cb62c6f53922de509))
* **ci:** delete R2 secrets on destroy-all to prevent stale credentials ([4564f6d](https://github.com/stefanko-ch/Nexus-Stack/commit/4564f6dec04678639b84b501c5838a9549805a6a))
* **ci:** Deploy Control Panel infrastructure before deploying Pages ([d9a8e6b](https://github.com/stefanko-ch/Nexus-Stack/commit/d9a8e6b9160dfae6de764f5582fbf1b5fa72676a))
* **ci:** Don't fail if auto-saving R2 secrets fails ([57b4082](https://github.com/stefanko-ch/Nexus-Stack/commit/57b40827cd0a7214c5324bfe323c3e671399f522))
* **ci:** Fix workflow concurrency deadlock and add validation ([bc2a8d3](https://github.com/stefanko-ch/Nexus-Stack/commit/bc2a8d37fb56583841703ac07654d150721cb12a))
* **ci:** Fix YAML heredoc indentation in setup-control-plane ([2f9739c](https://github.com/stefanko-ch/Nexus-Stack/commit/2f9739c5e3f8952e3c7a898ea12fb90019f028d5))
* **ci:** Force deployment to production environment ([adfb0cb](https://github.com/stefanko-ch/Nexus-Stack/commit/adfb0cb28b0b751ee08814d7e570289a2407e6df))
* **ci:** Force-set environment variables via API after Terraform ([172eed4](https://github.com/stefanko-ch/Nexus-Stack/commit/172eed4b725f847162bcb4b559f4927f27dd5dc1))
* **ci:** generate SSH key in GitHub Actions ([d0a8146](https://github.com/stefanko-ch/Nexus-Stack/commit/d0a814685265a9923fdfba10da12c48541cec066))
* **ci:** Improve auto-save of R2 secrets with better error handling ([2564686](https://github.com/stefanko-ch/Nexus-Stack/commit/2564686a8bd5761909a4f1f6ec155a9dd65cd17c))
* **ci:** Improve Control Panel environment variables setting ([bd78011](https://github.com/stefanko-ch/Nexus-Stack/commit/bd7801179325979018c081896c67c0115dfcdef6))
* **ci:** Improve environment variable setting with better error handling ([9a93c87](https://github.com/stefanko-ch/Nexus-Stack/commit/9a93c87faa49573176d944a50b98711499b34c12))
* **ci:** Improve error handling for secret operations ([99ea50c](https://github.com/stefanko-ch/Nexus-Stack/commit/99ea50c1579e1498c4b4655a31d7bc373d263ead))
* **ci:** Include commit body details in release changelog ([ec3019a](https://github.com/stefanko-ch/Nexus-Stack/commit/ec3019a6b36037e2357af90578020a23a1a333b8))
* **ci:** Include commit body details in release changelog ([89f30c3](https://github.com/stefanko-ch/Nexus-Stack/commit/89f30c3861c44049a0f3e3b39852b355e6521e49))
* **ci:** Indent wrangler heredoc in setup-control-plane ([56554bc](https://github.com/stefanko-ch/Nexus-Stack/commit/56554bc46a2f49c0645d039affca1bda2a270ae3))
* **ci:** Pass R2 credentials between workflows programmatically ([d200c28](https://github.com/stefanko-ch/Nexus-Stack/commit/d200c28a94ca23f48c7dc6c69a8a8cdb9373578f))
* **ci:** Properly merge environment variables for production and preview ([bdcec64](https://github.com/stefanko-ch/Nexus-Stack/commit/bdcec64bf1a2b06c90daaf8d25b1e514df43b9d9))
* **ci:** Re-apply Terraform after wrangler deploy to ensure KV bindings ([d606c46](https://github.com/stefanko-ch/Nexus-Stack/commit/d606c46186d8731a4bc5aedefa6a86620103460a))
* **ci:** Remove --commit-dirty flag from Wrangler deploy ([a143d15](https://github.com/stefanko-ch/Nexus-Stack/commit/a143d15d4b53e709473b7ebfb8d6cef10d01efff))
* **ci:** Remove concurrency from reusable workflows to prevent deadlock ([be0a428](https://github.com/stefanko-ch/Nexus-Stack/commit/be0a428c48eaab83edf2c5dd6f3c2a22fb34abd3))
* **ci:** Remove DNS record from Control Panel infrastructure targets ([2934fe9](https://github.com/stefanko-ch/Nexus-Stack/commit/2934fe9487f26dbde65d4e788493d7954a9b4397))
* **ci:** Remove duplicate Control Plane deploy from make up ([99096fe](https://github.com/stefanko-ch/Nexus-Stack/commit/99096fef27ab8907500639cdf0c6acea44953d25))
* **ci:** Remove send_credentials option from Spin Up workflow ([643dd29](https://github.com/stefanko-ch/Nexus-Stack/commit/643dd29709e0d4fd85936c8d1a1538f0f801f3fd))
* **ci:** Remove unsupported --env flag from wrangler deploy ([1c21691](https://github.com/stefanko-ch/Nexus-Stack/commit/1c216917e06728114248bd7255dc2d0c0db1fe6c))
* **ci:** Set Control Panel environment variables in deployment workflow ([860bdc6](https://github.com/stefanko-ch/Nexus-Stack/commit/860bdc618ac3530e76fe3b4cd9b4e40e1e4748a8))
* **ci:** Set environment variables for both production and preview ([05b2841](https://github.com/stefanko-ch/Nexus-Stack/commit/05b28415dad343214fe3532d325ec1e870402280))
* **ci:** Set environment variables for both production and preview ([f55a51f](https://github.com/stefanko-ch/Nexus-Stack/commit/f55a51f87bcbac6696ef706fd03f8d5e94bf1801))
* **ci:** Set GITHUB_TOKEN secret in Control Panel deployment ([8c5def8](https://github.com/stefanko-ch/Nexus-Stack/commit/8c5def8711d46d779f5d2728dee6f6bb2b648101))
* **ci:** Trim whitespace from R2 credentials to prevent auth errors ([092b29a](https://github.com/stefanko-ch/Nexus-Stack/commit/092b29ace0cebeeb356d5277f61d0eecffa38426))
* **ci:** Use Cloudflare API to set Control Panel environment variables ([1dea4a4](https://github.com/stefanko-ch/Nexus-Stack/commit/1dea4a4c19cd7a07367ac458698b329dca7b38d2))
* **ci:** Use GH_SECRETS_TOKEN instead of GITHUB_TOKEN ([b0912a8](https://github.com/stefanko-ch/Nexus-Stack/commit/b0912a8d9c17c0baa95e228ba3c53d56169f287e))
* **ci:** Use merge commits to identify PRs instead of date filter ([82d53d0](https://github.com/stefanko-ch/Nexus-Stack/commit/82d53d0b23b64c0b4e8088f6b1c2030fc845d7fc))
* **ci:** Use merge commits to identify PRs instead of date filter ([c0dd1f2](https://github.com/stefanko-ch/Nexus-Stack/commit/c0dd1f2245ab003a7b9236bf47550754863d4d3f))
* **ci:** Use PR titles for release notes instead of commits ([28fa260](https://github.com/stefanko-ch/Nexus-Stack/commit/28fa260c65018619c236c78630232aa0221b6930))
* **ci:** Use PR titles for release notes instead of commits ([89651b6](https://github.com/stefanko-ch/Nexus-Stack/commit/89651b697ce8f134309494008ce79afaac27b687))
* **ci:** Use single-line HTML to avoid YAML heredoc parsing issues ([01ebe54](https://github.com/stefanko-ch/Nexus-Stack/commit/01ebe5453e85a6835ea74879d02e846daf87dbb1))
* **ci:** Use single-line HTML to avoid YAML heredoc parsing issues ([24f080b](https://github.com/stefanko-ch/Nexus-Stack/commit/24f080baeaeb61a5b2007582c0267eabf7a0cbbc))
* **ci:** Use temp file for Python script to avoid YAML parsing issues ([a3a119b](https://github.com/stefanko-ch/Nexus-Stack/commit/a3a119b45bb1105f77e8e2455359bad98c009a85))
* **ci:** Use wrangler.toml for KV bindings instead of double deploy ([f37aa3b](https://github.com/stefanko-ch/Nexus-Stack/commit/f37aa3b67184967f32868f0d8515fd866f4e9a64))
* Clarify Cache-Control comment format ([df1526b](https://github.com/stefanko-ch/Nexus-Stack/commit/df1526b020cdab4e0d0212a470986b25be44cc6b))
* Clarify Stop vs Destroy workflow descriptions ([3c6a583](https://github.com/stefanko-ch/Nexus-Stack/commit/3c6a5831993a6df00d4fc31cbe288220c59562b6))
* Control Panel custom domain, logo distortion, add to Info Page ([e662312](https://github.com/stefanko-ch/Nexus-Stack/commit/e66231278009cf6f9ab316f89c8c3ff5b9c584ea))
* Control Panel error handling and disable unused stacks ([714b97b](https://github.com/stefanko-ch/Nexus-Stack/commit/714b97be23aad37b0850f70d786f1277887d7631))
* **control-panel:** Address PR review comments ([a5fc63f](https://github.com/stefanko-ch/Nexus-Stack/commit/a5fc63fd7cb68e5552b9c699eb4e025a460b5278))
* **control-panel:** Export CLOUDFLARE_API_TOKEN for wrangler commands ([a26d2fd](https://github.com/stefanko-ch/Nexus-Stack/commit/a26d2fd1b147c7f166e5bdce1f42ea0dbf9fe78f))
* **control-panel:** Fix Pages Functions deployment ([302df30](https://github.com/stefanko-ch/Nexus-Stack/commit/302df3071d8ba5be6cff6e0b0b791fb6de20d385))
* **control-panel:** Fix syntax error and improve workflow configuration ([f5cb801](https://github.com/stefanko-ch/Nexus-Stack/commit/f5cb80126152b5d810c103b0263d63cace566b5f))
* **control-panel:** Fix syntax error in info.js - missing closing brace for else block ([44a169e](https://github.com/stefanko-ch/Nexus-Stack/commit/44a169eeb9fba1d1521df31cb03b7e40838060a9))
* **control-panel:** Improve button state handling and error recovery ([839dd3c](https://github.com/stefanko-ch/Nexus-Stack/commit/839dd3cc74b00d12fa85ee087da9aedc4f941591))
* **control-panel:** Improve environment variable error handling and add setup script ([a132654](https://github.com/stefanko-ch/Nexus-Stack/commit/a13265447e957004e88b7389a3d95c747bae13a6))
* **control-panel:** Improve structure, error handling and deployment ([d3eb694](https://github.com/stefanko-ch/Nexus-Stack/commit/d3eb694f10ed947d90544aee1588107a9c3d3350))
* **control-panel:** Improve structure, error handling and deployment ([b661326](https://github.com/stefanko-ch/Nexus-Stack/commit/b6613263c59e4169ed68bad3c5723f7bddd8bb94))
* **control-panel:** Make Teardown and Destroy buttons always visible ([08edd0b](https://github.com/stefanko-ch/Nexus-Stack/commit/08edd0b80ea1f779bccffb64db1331a184830db8))
* **control-panel:** Move functions folder to project root ([5890515](https://github.com/stefanko-ch/Nexus-Stack/commit/58905152d160d620fc14bd519065b9a0aaf330cc))
* **control-panel:** Use secrets and fix token permissions ([e450298](https://github.com/stefanko-ch/Nexus-Stack/commit/e450298ab378b366c5c87bb376fe560bdff1130d))
* **control-plane:** Add ADMIN_EMAIL to Pages environment variables ([c4a8c7c](https://github.com/stefanko-ch/Nexus-Stack/commit/c4a8c7cdc20e1393aa9fbf3a6effa78a6529f0e5))
* **control-plane:** Improve UI states and scheduled teardown ([32d36d2](https://github.com/stefanko-ch/Nexus-Stack/commit/32d36d2033b76b24e9d1d3c33e5d05c95004c57b))
* **control-plane:** Replace Setup button with Email Credentials ([911f0c0](https://github.com/stefanko-ch/Nexus-Stack/commit/911f0c0fe1c9e2e70353bbc73a3abd0bd83fd534))
* **control-plane:** Swiss date format and footer with author ([ea33c09](https://github.com/stefanko-ch/Nexus-Stack/commit/ea33c094f290a5abcacd73f0a519a8839d2a06ef))
* **control-plane:** Use correct index.html with disabled service toggles ([ea0ea3e](https://github.com/stefanko-ch/Nexus-Stack/commit/ea0ea3e0d2e519890bfa51690ba55093196f7f91))
* **control-plane:** Use correct index.html with disabled service toggles ([6dd92b4](https://github.com/stefanko-ch/Nexus-Stack/commit/6dd92b4dbbec316da9752c28fdefb6fa71614cac))
* **control-plane:** Use European date format (dd.mm.yyyy, 24h) ([aa7d357](https://github.com/stefanko-ch/Nexus-Stack/commit/aa7d357642a1fe34c63376d2473d1d0b3c7a4888))
* Correct broken Docker image tags and add DOMAIN to global .env ([05edbd7](https://github.com/stefanko-ch/Nexus-Stack/commit/05edbd7101a0117bfc4a2a3913e249a51da56f7c))
* Correct Metabase image tag to v0.58.x ([f1acc74](https://github.com/stefanko-ch/Nexus-Stack/commit/f1acc74512e3d2cacc22fea375c4566a882fdb8e))
* Correct while loop closure in init-r2-state.sh ([c14dc9f](https://github.com/stefanko-ch/Nexus-Stack/commit/c14dc9f31c18de75a5008201d773a8639acbc9e2))
* **credentials:** Store and send actual credentials via KV ([1585e30](https://github.com/stefanko-ch/Nexus-Stack/commit/1585e304d72e8e7e6b0178857edf3261a1b3b3bc))
* Declare github_owner and github_repo in stack module ([669e424](https://github.com/stefanko-ch/Nexus-Stack/commit/669e4249454f8324cce7f1902d1fbf4105f2e9d8))
* Disable service toggles and remove refresh button ([878bbd8](https://github.com/stefanko-ch/Nexus-Stack/commit/878bbd884bb1435de50f60ab5d2381bd1e94724b))
* **email:** Only send Infisical credentials, hint to check Infisical for others ([4e75e27](https://github.com/stefanko-ch/Nexus-Stack/commit/4e75e274b2a8dcd68f6de0a7a8632897b4ac68c3))
* Enable CORS preflight bypass for Access API calls ([ea79096](https://github.com/stefanko-ch/Nexus-Stack/commit/ea79096c455f6eb3d17b00c5cfd8be6c09291371))
* Improve error handling and disable unused stacks ([c1dd1fa](https://github.com/stefanko-ch/Nexus-Stack/commit/c1dd1fa1c7fca5e0b9473b1ac274bfee01c086fc))
* Improve readability and error message clarity ([879c0af](https://github.com/stefanko-ch/Nexus-Stack/commit/879c0af7f54655882a99e92fa0820fd2a827d12a))
* Include Pages Functions in deployment ([dfd7999](https://github.com/stefanko-ch/Nexus-Stack/commit/dfd799940d2a92f7b7ea2080ebfee45f07a3cc68))
* Include Pages Functions in deployment ([02b7f3f](https://github.com/stefanko-ch/Nexus-Stack/commit/02b7f3ffebc2183d6766b25f368d35d6ea97bf55))
* Increase Service Token authentication retry buffer ([9c9a81f](https://github.com/stefanko-ch/Nexus-Stack/commit/9c9a81feb6ffb5805f78bfcb32f7c693a776dd23))
* **marimo:** Use correct PORT environment variable ([751b3d1](https://github.com/stefanko-ch/Nexus-Stack/commit/751b3d1c25c61e9b163e01a7baa3091216fce9de))
* Remove --commit-dirty flag and document preview/production difference ([553720e](https://github.com/stefanko-ch/Nexus-Stack/commit/553720eca60f5292771982fbb9e4cff25bc6b1d5))
* Remove credential masking to allow workflow output passing ([9af0d0c](https://github.com/stefanko-ch/Nexus-Stack/commit/9af0d0cb37381f919cb6c9bedd3992ae05d4948a))
* Remove duplicate Access Application causing 401 on API routes ([6b2e99c](https://github.com/stefanko-ch/Nexus-Stack/commit/6b2e99ccd4da16a648be2c46a5e53e3fcac0585f))
* Remove extra asterisks in README ([ea10187](https://github.com/stefanko-ch/Nexus-Stack/commit/ea101870b6d5a34e5795db1a4dca77a638782ad3))
* Remove incorrect fi statement in while loop ([05e73dd](https://github.com/stefanko-ch/Nexus-Stack/commit/05e73dd8dce7125e0847c9a5a98a3f6612759dd8))
* Remove redundant cloudflare_record.control_panel ([a0b8f66](https://github.com/stefanko-ch/Nexus-Stack/commit/a0b8f667d2a1b13fc5b76542780b3f81ceb01a83))
* Remove underscore from service name regex patterns ([d8bfbcb](https://github.com/stefanko-ch/Nexus-Stack/commit/d8bfbcb07987e4a0d1f6e370b4b217a84f9efdba))
* Restore logo size and add spinner to all buttons ([84f2c4d](https://github.com/stefanko-ch/Nexus-Stack/commit/84f2c4dd3c2e1eab69a9456cb7fcfcf697e983d7))
* Revert features emoji to 🚀 for consistency ([ae117c4](https://github.com/stefanko-ch/Nexus-Stack/commit/ae117c43762320f7fbc0bf95f9f2a8316cf84c01))
* **scripts:** Add retry logic for R2 token creation ([7643654](https://github.com/stefanko-ch/Nexus-Stack/commit/764365496f50e69e9c9ef4e957006b0e5c632838))
* **scripts:** Improve control panel secrets setup script ([ae9a1a5](https://github.com/stefanko-ch/Nexus-Stack/commit/ae9a1a548f836f14905e8d778903e39a8d4c27de))
* **scripts:** Update deploy.sh paths for tofu/stack directory ([551a75a](https://github.com/stefanko-ch/Nexus-Stack/commit/551a75aaca9d51626c708414c0aac688cf821461))
* **scripts:** Update generate-info-page.sh path for tofu/stack directory ([135a389](https://github.com/stefanko-ch/Nexus-Stack/commit/135a389ea1113410af443f7e4efd46f14e0bdf72))
* **scripts:** Use awk for precise SSH config block removal ([db25ebb](https://github.com/stefanko-ch/Nexus-Stack/commit/db25ebb6acee756391c42767f6114665b2da7996))
* **tofu:** Add missing CNAME record for Control Panel ([d2da426](https://github.com/stefanko-ch/Nexus-Stack/commit/d2da426a1cc17a0e10ae9df0ce42e5d61e29f698))
* **tofu:** Enable module format for scheduled teardown worker ([8c42e99](https://github.com/stefanko-ch/Nexus-Stack/commit/8c42e9985ce9ba388da1c508705ac735a1f41ed2))
* **tofu:** Fix cloudflare worker script syntax and add n8n to Infisical ([e7c02cd](https://github.com/stefanko-ch/Nexus-Stack/commit/e7c02cdc71533a453ffe77db135db29cf1ba8b97))
* **tofu:** Fix Terraform errors in control-panel configuration ([cfbfc29](https://github.com/stefanko-ch/Nexus-Stack/commit/cfbfc29c1049a02a40795d75c9e5d70dd3325430))
* **tofu:** Remove options_preflight_bypass (conflicts with cors_headers) ([f062192](https://github.com/stefanko-ch/Nexus-Stack/commit/f062192c7de3ffbde32621031b5cdaa5edd0c71c))
* **tofu:** Remove unsupported GitHub/Google OAuth blocks ([63a7f59](https://github.com/stefanko-ch/Nexus-Stack/commit/63a7f59bbe45efd2894c25b8859e8e0dc1c357a7))
* **tofu:** Update deprecated cloudflare_worker_cron_trigger to cloudflare_workers_cron_trigger ([167f7fd](https://github.com/stefanko-ch/Nexus-Stack/commit/167f7fde55ed1ea4f2c1cc8de2fca80f56ddd6a2))
* **ui:** Hide toggle for core services and fix info description ([f01d2ee](https://github.com/stefanko-ch/Nexus-Stack/commit/f01d2ee981c013f0e56530aee976807240a24b95))
* Use array for 'to' field and add error handling for Resend API ([df1c136](https://github.com/stefanko-ch/Nexus-Stack/commit/df1c136f9e1bf2692809d03f0b97b647c7967a16))
* Use clean UPPERCASE secret names in workflows ([b56eaf1](https://github.com/stefanko-ch/Nexus-Stack/commit/b56eaf1d399b586cbc7462454a69de833388340a))
* Use clean UPPERCASE secret names in workflows ([a332769](https://github.com/stefanko-ch/Nexus-Stack/commit/a3327695eb243b22dd9720d5245d4f6e0498fb72))
* Use correct cAdvisor image tag without v prefix ([88fc879](https://github.com/stefanko-ch/Nexus-Stack/commit/88fc87915e43376b35fc56b051bbd9314a268c2a))
* Use jq for proper JSON escaping in Resend email ([d1d718d](https://github.com/stefanko-ch/Nexus-Stack/commit/d1d718d325bd0daeac07df83bff56382b183661d))


### ♻️ Refactoring

* **ci:** Remove automatic cleanup tasks from deploy workflow ([4f3dd8b](https://github.com/stefanko-ch/Nexus-Stack/commit/4f3dd8b4da41b536a9553114af35800242d3eddf))
* **ci:** Remove unnecessary Infisical password storage in GitHub Secrets ([ebb4dec](https://github.com/stefanko-ch/Nexus-Stack/commit/ebb4decfb31bd5e1c6fcd9eb750df9b4928d4d7b))
* **ci:** Rename deploy workflow and add initial setup ([1438394](https://github.com/stefanko-ch/Nexus-Stack/commit/1438394fa4b60374d51f6a3145e3a1d846e6b3cd))
* **ci:** Rename deploy.yml to setup-control-plane.yaml ([14f21ee](https://github.com/stefanko-ch/Nexus-Stack/commit/14f21ee6f26e0028512f557cd2fd07c1a9313348))
* **ci:** Use secrets instead of environment variables for Control Panel ([18b2ad6](https://github.com/stefanko-ch/Nexus-Stack/commit/18b2ad65332afa8c4ff0228084195e2d1e5852e6))
* **ci:** use services.tfvars for service configuration ([0cb8118](https://github.com/stefanko-ch/Nexus-Stack/commit/0cb81181290fa9fdb70a3d50a241f26b0005ebf6))
* **ci:** use services.tfvars for service configuration ([8c5666d](https://github.com/stefanko-ch/Nexus-Stack/commit/8c5666d4d8ab3572d61a4776482a881a696d7bdb))
* **ci:** Use Terraform for Control Panel environment variables ([6d6dd89](https://github.com/stefanko-ch/Nexus-Stack/commit/6d6dd8940d2f15b89c6c53406ea20f76d7d04036))
* Decouple Setup and Spin Up workflows ([a234c38](https://github.com/stefanko-ch/Nexus-Stack/commit/a234c385abb21bb8a231dd65f0d5f752a9606677))
* Remove browser login fallback for GitHub Actions ([3f2f40f](https://github.com/stefanko-ch/Nexus-Stack/commit/3f2f40f269d85ea13907022a1562397580077a56))
* Remove unused authentication methods configuration ([c4c97fe](https://github.com/stefanko-ch/Nexus-Stack/commit/c4c97fe84b555fa3c8d9be258530db326277e8b5))
* Rename Control Panel to Control Plane ([9fcd024](https://github.com/stefanko-ch/Nexus-Stack/commit/9fcd024aab7ca59ab156fbc464ec91df91370531))
* Rename Control Panel to Control Plane ([91206e1](https://github.com/stefanko-ch/Nexus-Stack/commit/91206e14927bb69a3fcf9470512dafc5c1cc3eeb))
* Rename workflow names for clarity ([1b306b1](https://github.com/stefanko-ch/Nexus-Stack/commit/1b306b183ced7deb8601f601b9fca495c31c6efa))
* Rename workflows and improve CI config handling ([931e5ff](https://github.com/stefanko-ch/Nexus-Stack/commit/931e5ffe3522a06ddcceea4c47fa13fd72099a81))
* **scripts:** Add exponential backoff for Service Token auth ([961158c](https://github.com/stefanko-ch/Nexus-Stack/commit/961158c96866f467129d3e0e2cb3918a17aab03e))
* **services:** Store enabled status in KV instead of Git ([ae486f9](https://github.com/stefanko-ch/Nexus-Stack/commit/ae486f9acf1120165540f0d0ac6ed5113f031182))
* **tofu:** Split Terraform state into Control Plane and Nexus Stack ([b0d2648](https://github.com/stefanko-ch/Nexus-Stack/commit/b0d26487db754552f3397f066692e1d89a7b63cd))
* Use major version pinning for Docker images ([27eb324](https://github.com/stefanko-ch/Nexus-Stack/commit/27eb3240f0463cc41c34036c4d53a818b9558b68))


### ⚡ Performance

* **scripts:** Optimize deployment pipeline ([cfbfc29](https://github.com/stefanko-ch/Nexus-Stack/commit/cfbfc29c1049a02a40795d75c9e5d70dd3325430))


### 📚 Documentation

* Add Authentication Methods feature documentation ([0b5b2b5](https://github.com/stefanko-ch/Nexus-Stack/commit/0b5b2b509d33607dcb87d163dcce67ff7f48cfeb))
* Add Contents: Read permission requirement for Fine-Grained Tokens ([26b7b4c](https://github.com/stefanko-ch/Nexus-Stack/commit/26b7b4c7396338bdb8b79adc4478db020ad4230b))
* Add detailed Resend email setup guide ([1d8109e](https://github.com/stefanko-ch/Nexus-Stack/commit/1d8109ee9d0613b155c12953638fca064faee86c))
* Add Docker Hub credentials setup guide ([b975abe](https://github.com/stefanko-ch/Nexus-Stack/commit/b975abefd1d6b96586659c1c91d41cb5d5d28d81))
* Add Docker image versions table to stacks documentation ([c518b3f](https://github.com/stefanko-ch/Nexus-Stack/commit/c518b3f1340d7a3f8d8453dd9e0a19b2608bb0de))
* Add gh api command for replying to PR review comments ([70f61cb](https://github.com/stefanko-ch/Nexus-Stack/commit/70f61cb497b8cec75287ee72e5f7bda9684168bc))
* Add GitHub and GitHub Actions badges ([655529d](https://github.com/stefanko-ch/Nexus-Stack/commit/655529d2e00a6c6901f8b4466140071f7773a6e9))
* Add GitHub Copilot instructions file ([24c1259](https://github.com/stefanko-ch/Nexus-Stack/commit/24c12593b51d1292829de531cdb8d1218ef42255))
* Add instruction to reply individually to PR review comments ([f02a950](https://github.com/stefanko-ch/Nexus-Stack/commit/f02a950fdb58017540ff1843e7f8089415d94a43))
* Add note about Control Panel environment variables setup ([38e9dc2](https://github.com/stefanko-ch/Nexus-Stack/commit/38e9dc2de33998c3b22b6409e8a88869879a5264))
* Add Workers KV Storage permission and permission check script ([5689eca](https://github.com/stefanko-ch/Nexus-Stack/commit/5689eca26ce918e7c3b16e5d9246c2e371a9a6f0))
* Add Workers Scripts permission requirement for Cloudflare API token ([d2b91bf](https://github.com/stefanko-ch/Nexus-Stack/commit/d2b91bf7cdfc0902c820acd92084c0556e78f367))
* Add Workers Scripts permission to README.md ([ef3201f](https://github.com/stefanko-ch/Nexus-Stack/commit/ef3201fac442a385009c4404685fa24955e1c888))
* **ci:** Add do not reply notice to credentials email ([9ed550d](https://github.com/stefanko-ch/Nexus-Stack/commit/9ed550d2331fcd264edc5fa23c5b9a272c48de5c))
* **ci:** Add website sync trigger to release workflow ([a76fc96](https://github.com/stefanko-ch/Nexus-Stack/commit/a76fc96f6d26a8ac2cdc250bc1c58a11d573cbe0))
* **ci:** Add website sync trigger to release workflow ([25abd9e](https://github.com/stefanko-ch/Nexus-Stack/commit/25abd9e47f03e0dce78897ab7a0a627823583896))
* **ci:** Clarify email login in credentials email ([7609172](https://github.com/stefanko-ch/Nexus-Stack/commit/7609172be107106631285b04e38a636eeb0bc979))
* Clarify Fine-Grained Token requirements ([f76aa0a](https://github.com/stefanko-ch/Nexus-Stack/commit/f76aa0a1e062ee6798d0cb8f5b763b87c21421ed))
* Clarify legacy /api/deploy endpoint ([ecc0706](https://github.com/stefanko-ch/Nexus-Stack/commit/ecc07061183a9a5c49e4ed53a4f87a0e2dd18bee))
* **scripts:** Update Cloudflare Pages logs command examples ([a85a26e](https://github.com/stefanko-ch/Nexus-Stack/commit/a85a26e3d94b6d5579b1fa030e94722ccad83d60))
* Streamline README and move details to docs ([a699880](https://github.com/stefanko-ch/Nexus-Stack/commit/a699880240b202fcd43935577cf03f88b3b863cd))
* **tofu:** Add authentication methods configuration example ([54d496d](https://github.com/stefanko-ch/Nexus-Stack/commit/54d496d105cc754e3ca80042a89c66438b942a1e))
* Update GitHub Token requirements documentation ([01014a0](https://github.com/stefanko-ch/Nexus-Stack/commit/01014a0e67342d7c93aa05efb1b22b292482c997))
* update README with auto-save R2 credentials ([8c6d9f3](https://github.com/stefanko-ch/Nexus-Stack/commit/8c6d9f3bfbba15128d41cad1d338d85a8cac46d2))
* update README with auto-save R2 credentials via GH_SECRETS_TOKEN ([5827d89](https://github.com/stefanko-ch/Nexus-Stack/commit/5827d894f106848037c85c39a8a610ca983684fe))


### 🔧 Maintenance

* Add workflow validation CI ([c804fde](https://github.com/stefanko-ch/Nexus-Stack/commit/c804fdecb7238b9e6b4398bb6158638836fe2b38))
* Configure Release Please for v1.x releases ([0c91ad8](https://github.com/stefanko-ch/Nexus-Stack/commit/0c91ad8324aede093d2df1e5566c61743f464d63))
* Configure Release Please to bump minor for breaking changes ([6fd849c](https://github.com/stefanko-ch/Nexus-Stack/commit/6fd849c537c5255b67781e2f9287b004d1e3d663))
* **main:** release 0.22.1 ([f435dc5](https://github.com/stefanko-ch/Nexus-Stack/commit/f435dc5f432bd6c5a4933039090e07808d5572ab))
* **main:** release 0.22.1 ([769daaf](https://github.com/stefanko-ch/Nexus-Stack/commit/769daaffa2d38fe089a947eb57fdc7788be7a1ab))
* Migrate to Release Please for automated releases ([3966ca8](https://github.com/stefanko-ch/Nexus-Stack/commit/3966ca83c1065a74470637b4808b194f05897339))
* Migrate to Release Please for automated releases ([c860634](https://github.com/stefanko-ch/Nexus-Stack/commit/c86063442ee91698d07cf0d5266fa1b0f797a4a4))
* Remove Cloudflare permissions test script ([0e0447d](https://github.com/stefanko-ch/Nexus-Stack/commit/0e0447d995c4f65c795c55e0e9751ef6da0b965e))
* Remove obsolete control-panel directory ([695ae5d](https://github.com/stefanko-ch/Nexus-Stack/commit/695ae5dd522baa3ec2b57d2dd391293773e2388e))
* Reset to v0.1.0 for proper semver ([b107824](https://github.com/stefanko-ch/Nexus-Stack/commit/b10782433facfb2617ac9ac2f8f7a1f274121f8d))
* Reset to v0.1.0 for proper semver progression ([64bfa1d](https://github.com/stefanko-ch/Nexus-Stack/commit/64bfa1d5c2f03feac30f16eea0b90d757a012c2e))
* Reset to v1.0.0 - clean slate ([439cb1d](https://github.com/stefanko-ch/Nexus-Stack/commit/439cb1d09413c2f2c801bdcb9ec0e3a705bdc33a))
* Reset to v1.0.0 - clean slate ([dfaead3](https://github.com/stefanko-ch/Nexus-Stack/commit/dfaead305453b3cc5d5f634238528e4e579c4c02))

## [0.1.0](https://github.com/stefanko-ch/Nexus-Stack/releases/tag/v0.1.0) (2026-01-16)

### Initial Release

Nexus-Stack v0.1.0 - One-command deployment of Docker services on Hetzner Cloud with Cloudflare Zero Trust protection.

### Features

- **Infrastructure as Code**: OpenTofu/Terraform configuration for Hetzner Cloud
- **Zero Trust Security**: All traffic through Cloudflare Tunnel, no open ports
- **Control Plane**: Web UI for managing deployments
- **GitHub Actions**: Automated workflows for deployment

### Available Stacks

Portainer, Grafana, Prometheus, Loki, n8n, Kestra, Uptime Kuma, IT-Tools, Excalidraw, Mailpit, Infisical, Metabase, Marimo
