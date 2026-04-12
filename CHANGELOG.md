# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.46.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.45.2...v0.46.0) (2026-04-12)


### ⚠ BREAKING CHANGES

* **firewall:** RedPanda now runs in production mode instead of dev-container mode

### 🚀 Features

* Add connection test and sync status to Databricks integration ([b163728](https://github.com/stefanko-ch/Nexus-Stack/commit/b163728386910f5b6886096a59e3e99cb8e0f8cb))
* Add external S3/R2 storage auto-mount for Filestash ([fd1807d](https://github.com/stefanko-ch/Nexus-Stack/commit/fd1807d77ff3d3310364b008cb6be25665ccb692)), closes [#261](https://github.com/stefanko-ch/Nexus-Stack/issues/261)
* Add R2 datalake bucket with auto-Filestash integration ([a74fd1f](https://github.com/stefanko-ch/Nexus-Stack/commit/a74fd1fb58e5a606b766ac863c087964bbf5c026))
* Add R2 datalake bucket with auto-Filestash integration ([1e53fdf](https://github.com/stefanko-ch/Nexus-Stack/commit/1e53fdf8440bbcb4444adbdd839e00d43aa7d1ee))
* **control-plane:** Add admin_only flag to prevent users from toggling Wetty ([a6b3696](https://github.com/stefanko-ch/Nexus-Stack/commit/a6b36966ad0d610f45aee17de8f15a01eefc5d09))
* **control-plane:** Add email notification toggles ([98d6021](https://github.com/stefanko-ch/Nexus-Stack/commit/98d6021b4c1fd70560dea1c4d6c81eb204223280))
* **control-plane:** Add limits and audit logging to teardown extensions ([84173f8](https://github.com/stefanko-ch/Nexus-Stack/commit/84173f83d739e222c4ac9c0a32ae8b3ca7e78bd5))
* **control-plane:** Add limits and audit logging to teardown extensions ([fa72e91](https://github.com/stefanko-ch/Nexus-Stack/commit/fa72e916a5ca9945acd51856e574c9581128dd82)), closes [#340](https://github.com/stefanko-ch/Nexus-Stack/issues/340)
* **control-plane:** Add post-deploy diagnostic health check for worker ([61c5254](https://github.com/stefanko-ch/Nexus-Stack/commit/61c52546f7faaa47acb9f867bf6821bc91a13d6b))
* **control-plane:** Add PUBLIC warning badge for public services ([5901057](https://github.com/stefanko-ch/Nexus-Stack/commit/5901057b676b7ff947239952e938648352317291))
* **control-plane:** Add Secrets page with grouped, masked credentials ([43a6013](https://github.com/stefanko-ch/Nexus-Stack/commit/43a6013b433b52d0c815bd046d53c353f3a1d298))
* **control-plane:** Add Silent Mode to suppress automated emails ([1e93a44](https://github.com/stefanko-ch/Nexus-Stack/commit/1e93a44cd2a4c05f29074289688f3d0af5725f06)), closes [#242](https://github.com/stefanko-ch/Nexus-Stack/issues/242)
* **control-plane:** Email notification toggles and Silent Mode ([6758583](https://github.com/stefanko-ch/Nexus-Stack/commit/675858369e23281e8591f2ed1bbe401450d55337))
* **control-plane:** Fetch secrets live from Infisical API instead of static JSON ([d8d81c4](https://github.com/stefanko-ch/Nexus-Stack/commit/d8d81c443a96e39d95a8c0c599615af096b0d9d7))
* **control-plane:** Redesign Control Panel with category-based navigation ([89998c5](https://github.com/stefanko-ch/Nexus-Stack/commit/89998c5c7be9483c4b722903dd0b080d99454157))
* **control-plane:** Remove info page, add Open links to service cards ([9ced111](https://github.com/stefanko-ch/Nexus-Stack/commit/9ced111ed080aa0140755a04a2c1f01f9ea98805))
* **control-plane:** Show silent mode state in email toggles UI ([c006faa](https://github.com/stefanko-ch/Nexus-Stack/commit/c006faa097d92df092fcaf9b3f2a63b1b1aa1ccc))
* **docs:** Add website sync workflow and frontmatter for nexus-stack.ch ([b235cbf](https://github.com/stefanko-ch/Nexus-Stack/commit/b235cbf54efc856aa8b1b040e0db32949781c174))
* **docs:** Add website sync workflow and frontmatter to all docs ([56a7e8a](https://github.com/stefanko-ch/Nexus-Stack/commit/56a7e8a22094662abd9137e951306384a06674fc)), closes [#399](https://github.com/stefanko-ch/Nexus-Stack/issues/399)
* External S3 storage, Infisical folders, and volume protection ([67fa4fd](https://github.com/stefanko-ch/Nexus-Stack/commit/67fa4fdabfafb4d60c7eb97eab2d9f42e86b1820))
* **firewall:** Add Firewall Management for external TCP access ([#174](https://github.com/stefanko-ch/Nexus-Stack/issues/174)) ([7be3a70](https://github.com/stefanko-ch/Nexus-Stack/commit/7be3a70aeaecb6c1735fc7a92b08f709b0a2f63f))
* Push external S3/R2 credentials to Infisical ([368135a](https://github.com/stefanko-ch/Nexus-Stack/commit/368135a8601a5d197611ffcee353f0616f7f4ea2))
* Push Hetzner Object Storage credentials to Infisical ([cfc5fe8](https://github.com/stefanko-ch/Nexus-Stack/commit/cfc5fe8d915be375f7f03bce9b7960a262d52131))
* **stacks:** Add 5 object storage stacks (Filestash, Garage, LakeFS, RustFS, SeaweedFS) ([#184](https://github.com/stefanko-ch/Nexus-Stack/issues/184)) ([c1c3825](https://github.com/stefanko-ch/Nexus-Stack/commit/c1c3825bf702b1fdcf181772d8e602d698bb7274))
* **stacks:** Add AKHQ Kafka/Redpanda management GUI ([c4fad8b](https://github.com/stefanko-ch/Nexus-Stack/commit/c4fad8ba0712f7c4a7a1d874e4cafb394ef9c8c6))
* **stacks:** Add AKHQ Kafka/Redpanda management GUI ([f28c9b7](https://github.com/stefanko-ch/Nexus-Stack/commit/f28c9b75520b731e81b811cbcd4ffdeaac6fdb2c)), closes [#41](https://github.com/stefanko-ch/Nexus-Stack/issues/41)
* **stacks:** Add Apache Flink stack + fix Control Plane env vars ([c28e1bc](https://github.com/stefanko-ch/Nexus-Stack/commit/c28e1bc3d671be740727674bb9f5e948671c800f))
* **stacks:** Add Apache Flink stream processing stack ([b058b3b](https://github.com/stefanko-ch/Nexus-Stack/commit/b058b3b77166da40188fec15be374c3a8c219c83))
* **stacks:** Add Apache Spark cluster and upgrade Jupyter to PySpark ([e897ed7](https://github.com/stefanko-ch/Nexus-Stack/commit/e897ed73cd225ad2e0fd2161b446c61655e56c9f))
* **stacks:** Add Apache Spark cluster with PySpark Jupyter integration ([e476c44](https://github.com/stefanko-ch/Nexus-Stack/commit/e476c44912731ac869d10d0f1103cf3ee6b0061b))
* **stacks:** Add Apache Superset data exploration platform ([7f38ed2](https://github.com/stefanko-ch/Nexus-Stack/commit/7f38ed242d53a2c6f432c3c65558bf192d485fbf))
* **stacks:** Add Apache Superset stack, fetch Control Plane secrets from Infisical ([7dd6c45](https://github.com/stefanko-ch/Nexus-Stack/commit/7dd6c45836dd617bc296fc988b1830665aca41b1))
* **stacks:** Add Appsmith low-code platform ([2e08d47](https://github.com/stefanko-ch/Nexus-Stack/commit/2e08d47b48cb8203efb0a5bb7b7628bb55b2f397))
* **stacks:** Add Appsmith low-code platform ([c805799](https://github.com/stefanko-ch/Nexus-Stack/commit/c805799c1c2290bb4328d4bf3288f740887aca73))
* **stacks:** Add Budibase low-code platform ([dc60df7](https://github.com/stefanko-ch/Nexus-Stack/commit/dc60df7f68b35a36a3baedb9b290f474b6cffd30))
* **stacks:** Add Budibase low-code platform ([c807f99](https://github.com/stefanko-ch/Nexus-Stack/commit/c807f994b0179b45057f9d5dff905bc7427a3306)), closes [#246](https://github.com/stefanko-ch/Nexus-Stack/issues/246)
* **stacks:** Add ClickHouse analytics database ([1d09565](https://github.com/stefanko-ch/Nexus-Stack/commit/1d095654764830ed14ad7b81d6176f433c35c85d))
* **stacks:** Add ClickHouse analytics database ([9a30f9c](https://github.com/stefanko-ch/Nexus-Stack/commit/9a30f9c1650b8133f783783b9bd353abb5af36c6)), closes [#26](https://github.com/stefanko-ch/Nexus-Stack/issues/26)
* **stacks:** Add Dagster data orchestration platform ([85db108](https://github.com/stefanko-ch/Nexus-Stack/commit/85db108cd037dc380bccf3e20490a05690ef9512))
* **stacks:** Add Dagster data orchestration platform ([8ae9a3c](https://github.com/stefanko-ch/Nexus-Stack/commit/8ae9a3c01976709c6c3d3dfb536ce4bf55248959)), closes [#161](https://github.com/stefanko-ch/Nexus-Stack/issues/161)
* **stacks:** Add Debezium CDC platform ([b552997](https://github.com/stefanko-ch/Nexus-Stack/commit/b552997e3d6ed6547579be7c03112cbaf2bcaf9a))
* **stacks:** Add Debezium CDC platform ([4aaf153](https://github.com/stefanko-ch/Nexus-Stack/commit/4aaf15383e462211b93523690dd5a28db4da428d)), closes [#235](https://github.com/stefanko-ch/Nexus-Stack/issues/235)
* **stacks:** Add dedicated PySpark kernel to Jupyter ([425e64f](https://github.com/stefanko-ch/Nexus-Stack/commit/425e64f008cf7d9a4702eddc125d143541329b32))
* **stacks:** Add Dify AI workflow builder platform ([a0b5546](https://github.com/stefanko-ch/Nexus-Stack/commit/a0b5546a6a44f57de963517a50af35224ff94f34))
* **stacks:** Add Dify AI workflow builder platform ([4fe76ab](https://github.com/stefanko-ch/Nexus-Stack/commit/4fe76ab2a443ac671ccb447382957e1b6d86bbc1)), closes [#220](https://github.com/stefanko-ch/Nexus-Stack/issues/220)
* **stacks:** Add Dinky Flink SQL IDE ([3e1f213](https://github.com/stefanko-ch/Nexus-Stack/commit/3e1f213e6ce630ce79996a122b8d6c8ec76f6099))
* **stacks:** Add Dinky Flink SQL IDE ([9e65bb1](https://github.com/stefanko-ch/Nexus-Stack/commit/9e65bb1e3ba200f5764bfa94edfab3fd29c4a24e)), closes [#294](https://github.com/stefanko-ch/Nexus-Stack/issues/294)
* **stacks:** Add Docker resource limits to Spark containers ([5f7d442](https://github.com/stefanko-ch/Nexus-Stack/commit/5f7d4422b2cbc41bd16e84e9a33d7a1e38aab9c2))
* **stacks:** add Git proxy, auto-repo creation, and service Git bindings ([b84cc12](https://github.com/stefanko-ch/Nexus-Stack/commit/b84cc125ad9cb4389f7ec596c51ed1c6f9077edd))
* **stacks:** Add Gitea Git integration with proxy, user accounts, and service bindings ([77e3a09](https://github.com/stefanko-ch/Nexus-Stack/commit/77e3a098edb8d780e5eecc7c290e0f9741c7980c))
* **stacks:** Add Gitea stack with persistent Hetzner Cloud Volume ([2c19012](https://github.com/stefanko-ch/Nexus-Stack/commit/2c19012ae7f22faf0e6398b5e4927707a527d184)), closes [#158](https://github.com/stefanko-ch/Nexus-Stack/issues/158)
* **stacks:** Add Gitea stack with persistent volume and fix scheduled teardown ([b708fd5](https://github.com/stefanko-ch/Nexus-Stack/commit/b708fd51d9c3816a071acfbd650f5134107455e1))
* **stacks:** Add Gitea user account, private repo, and Infisical secrets ([e516c88](https://github.com/stefanko-ch/Nexus-Stack/commit/e516c8869133d56a1a49fa2a95ce0a0135b5a96c))
* **stacks:** Add Jupyter and code-server stacks ([feae842](https://github.com/stefanko-ch/Nexus-Stack/commit/feae84246649ba0a82535c4ad1a341a328627839)), closes [#31](https://github.com/stefanko-ch/Nexus-Stack/issues/31) [#45](https://github.com/stefanko-ch/Nexus-Stack/issues/45)
* **stacks:** Add Jupyter and code-server with pre-configured auth ([bf946c0](https://github.com/stefanko-ch/Nexus-Stack/commit/bf946c05ce818b703047a7dcb35907f75d0546ce))
* **stacks:** Add Kafdrop Kafka/Redpanda web UI ([4ad8a00](https://github.com/stefanko-ch/Nexus-Stack/commit/4ad8a0001f04085e07cf6338a8691c1b790f18ad))
* **stacks:** Add Kafdrop Kafka/Redpanda web UI ([951f8ae](https://github.com/stefanko-ch/Nexus-Stack/commit/951f8ae2ff255a6aad5a04501b0b2cd7c7b45544)), closes [#40](https://github.com/stefanko-ch/Nexus-Stack/issues/40)
* **stacks:** Add NocoDB open-source Airtable alternative ([135f5b5](https://github.com/stefanko-ch/Nexus-Stack/commit/135f5b5bd6624129f36704f7aad7bca7e262cee4))
* **stacks:** Add Ollama + Open WebUI stack ([01bc881](https://github.com/stefanko-ch/Nexus-Stack/commit/01bc881319cb8a63caa1342e6f6b2f4516a6585f))
* **stacks:** Add Ollama + Open WebUI stack ([5e798ea](https://github.com/stefanko-ch/Nexus-Stack/commit/5e798ea68ddc50ce768c8a2064a36393cb144e1a)), closes [#217](https://github.com/stefanko-ch/Nexus-Stack/issues/217)
* **stacks:** Add OpenMetadata data catalog stack ([351f928](https://github.com/stefanko-ch/Nexus-Stack/commit/351f928443aa41880d39ca3c2db4242a95e66340))
* **stacks:** Add OpenMetadata data catalog stack ([04ac3f5](https://github.com/stefanko-ch/Nexus-Stack/commit/04ac3f5c120170493a9202a229ac3cd361ac9242)), closes [#84](https://github.com/stefanko-ch/Nexus-Stack/issues/84)
* **stacks:** Add optional GitHub-to-Gitea repository mirroring ([9f3bc26](https://github.com/stefanko-ch/Nexus-Stack/commit/9f3bc26e61dff7884b62dc2c0c120769f0b55b7b))
* **stacks:** Add optional GitHub→Gitea repository mirroring ([73e2510](https://github.com/stefanko-ch/Nexus-Stack/commit/73e25108aef3cf5e97bfa90457e5b55142e460d7))
* **stacks:** Add optional workspace Git repo fork with custom naming ([1c01444](https://github.com/stefanko-ch/Nexus-Stack/commit/1c01444457374ab4c0d6fe4a672689b0915c6fa7))
* **stacks:** Add pg_ducklake - PostgreSQL with DuckLake extension ([7cf0ade](https://github.com/stefanko-ch/Nexus-Stack/commit/7cf0aded8f8848ef0e2a0a569caa97135d847114))
* **stacks:** Add pg_ducklake - PostgreSQL with DuckLake extension ([9699124](https://github.com/stefanko-ch/Nexus-Stack/commit/9699124a781b2a79f28d9eb423c8ccd9f29c340a)), closes [#331](https://github.com/stefanko-ch/Nexus-Stack/issues/331)
* **stacks:** Add Prefect workflow orchestration platform ([c8cd05f](https://github.com/stefanko-ch/Nexus-Stack/commit/c8cd05f6a205986d27f76d70c0171b34ef81dc01))
* **stacks:** Add Prefect workflow orchestration platform ([ed6c54e](https://github.com/stefanko-ch/Nexus-Stack/commit/ed6c54ebc0d49bc7176f26c315961ef0b48a1cbe))
* **stacks:** Add PySpark starter notebook to Jupyter ([3a75f2f](https://github.com/stefanko-ch/Nexus-Stack/commit/3a75f2fbadd9933af44a5c033bbfae8fa336f581))
* **stacks:** Add Python, uv, and Jupyter to code-server ([c6acbec](https://github.com/stefanko-ch/Nexus-Stack/commit/c6acbec1942b4804cbe6f3f449dc366732ce47fb))
* **stacks:** Add Python, uv, and Jupyter to code-server ([5eb9021](https://github.com/stefanko-ch/Nexus-Stack/commit/5eb9021e78ca41e45182578753f4db515da7c674))
* **stacks:** Add Quickwit cloud-native log search engine ([23d3c82](https://github.com/stefanko-ch/Nexus-Stack/commit/23d3c8295d3eacbb7be4facd6cfec2e0384dea2b))
* **stacks:** Add Quickwit log search and NocoDB Airtable alternative ([302a515](https://github.com/stefanko-ch/Nexus-Stack/commit/302a5154cfc7761c21508ba7c7969c2e180f8a75))
* **stacks:** Add RisingWave streaming database ([cfe4862](https://github.com/stefanko-ch/Nexus-Stack/commit/cfe486238f9b6f0a7fd8da782da43f2b5f21023e))
* **stacks:** Add RisingWave streaming database ([a9d3868](https://github.com/stefanko-ch/Nexus-Stack/commit/a9d386877a04c184f1b4b0a2d3c8aad30de22534)), closes [#284](https://github.com/stefanko-ch/Nexus-Stack/issues/284)
* **stacks:** Add S3 bucket access to Spark/Jupyter starter notebook ([a48d0c8](https://github.com/stefanko-ch/Nexus-Stack/commit/a48d0c8533308983c9e1b8f8e8fc3c308907cb38))
* **stacks:** Add S3 Manager web UI for object storage ([9c360dd](https://github.com/stefanko-ch/Nexus-Stack/commit/9c360ddecf1fe65aaf63307ef9e51ed441ad27a7))
* **stacks:** Add S3 Manager web UI for object storage ([51a66eb](https://github.com/stefanko-ch/Nexus-Stack/commit/51a66eb90621de690255fd1d5bcb36289772dc53)), closes [#215](https://github.com/stefanko-ch/Nexus-Stack/issues/215)
* **stacks:** Add Sling data integration CLI tool ([7e005ec](https://github.com/stefanko-ch/Nexus-Stack/commit/7e005ec7b3c44b5784fdd34ea60045600a55d960))
* **stacks:** Add Sling data integration CLI tool ([29d10b0](https://github.com/stefanko-ch/Nexus-Stack/commit/29d10b0e46219ba7d4c03eb58be3b4e9ead0a833)), closes [#311](https://github.com/stefanko-ch/Nexus-Stack/issues/311)
* **stacks:** Add Soda Core data quality stack ([6984c50](https://github.com/stefanko-ch/Nexus-Stack/commit/6984c5087c5396dd147cf961d75e387171baf4e0))
* **stacks:** Add Trino distributed SQL query engine ([51ffccb](https://github.com/stefanko-ch/Nexus-Stack/commit/51ffccba3e6e2853cbad9a59c56c892544eab36a))
* **stacks:** Add Trino distributed SQL query engine ([bb4aa30](https://github.com/stefanko-ch/Nexus-Stack/commit/bb4aa305dddecff2894f61dd1d4d1cdd0c7bbf81)), closes [#91](https://github.com/stefanko-ch/Nexus-Stack/issues/91)
* **stacks:** Add Vector and Telegraf observability agents ([3dd73b1](https://github.com/stefanko-ch/Nexus-Stack/commit/3dd73b117471bde64361c8be48ac8f353674e7c7))
* **stacks:** Add Vector and Telegraf observability agents ([d09f92e](https://github.com/stefanko-ch/Nexus-Stack/commit/d09f92ece9a8d9e01824e434a086b437a29add26)), closes [#316](https://github.com/stefanko-ch/Nexus-Stack/issues/316) [#317](https://github.com/stefanko-ch/Nexus-Stack/issues/317)
* **stacks:** Add Wiki.js knowledge base stack ([f31db5d](https://github.com/stefanko-ch/Nexus-Stack/commit/f31db5d0ffadd0444125144f631c33e8e5b18f94))
* **stacks:** Add Wiki.js stack + CI/CD resilience fixes ([fe7f855](https://github.com/stefanko-ch/Nexus-Stack/commit/fe7f855a376a3bf57971070f47ddccbf23724f11))
* **stacks:** Add Windmill workflow engine stack ([1db4e7f](https://github.com/stefanko-ch/Nexus-Stack/commit/1db4e7f647413f75f49506d48e25377f272c4c5d))
* **stacks:** Add Windmill workflow engine stack ([e436710](https://github.com/stefanko-ch/Nexus-Stack/commit/e436710509ac573e4720b392f2e6988889a7da44)), closes [#176](https://github.com/stefanko-ch/Nexus-Stack/issues/176)
* **stacks:** Add Woodpecker CI stack ([9dc3726](https://github.com/stefanko-ch/Nexus-Stack/commit/9dc37268af02a194d1d7f5cd96eb89a833d83ee8))
* **stacks:** Add Woodpecker CI stack ([a272e2b](https://github.com/stefanko-ch/Nexus-Stack/commit/a272e2b1ef1a2152ffe0c87769ae7460722b0d42))
* **stacks:** Add workspace Git repo fork from GitHub mirror ([f7afb7a](https://github.com/stefanko-ch/Nexus-Stack/commit/f7afb7afb571ab8bd578b4a5f299a2071ed40f7e))
* **stacks:** Bake Kafka SQL connector into Dinky image ([f945f8f](https://github.com/stefanko-ch/Nexus-Stack/commit/f945f8f529a92bde6b70c1502f72873a7120457f))
* **stacks:** Bake Kafka SQL connector into Flink image ([e305ac3](https://github.com/stefanko-ch/Nexus-Stack/commit/e305ac38db4251ad7ecc587982792e4b9469e105))
* **stacks:** Enable Grafana anonymous access with Viewer role ([6cb3aa8](https://github.com/stefanko-ch/Nexus-Stack/commit/6cb3aa817c0a835365913d92646bdbe7438266c6)), closes [#233](https://github.com/stefanko-ch/Nexus-Stack/issues/233)
* **stacks:** Grafana anonymous access (skip double login) ([7304255](https://github.com/stefanko-ch/Nexus-Stack/commit/73042551bfddc6fdd5fe5c46fa9ad0afb93d04e4))
* **stacks:** Make Grafana a core service for always-on monitoring ([e63beda](https://github.com/stefanko-ch/Nexus-Stack/commit/e63bedab39ce6962ba26f79ab8c4d332f7e180b5))
* **stacks:** Switch Redpanda Connect to streams mode ([47506fb](https://github.com/stefanko-ch/Nexus-Stack/commit/47506fbeff02fda465591901722e65610c69fa1c))
* Sync Infisical secrets to Databricks Secret Scopes ([8182a7b](https://github.com/stefanko-ch/Nexus-Stack/commit/8182a7bbb136edef1d7c423d39066e3d942fa8a8)), closes [#175](https://github.com/stefanko-ch/Nexus-Stack/issues/175)
* Sync Infisical secrets to Databricks via Control Panel ([12fa194](https://github.com/stefanko-ch/Nexus-Stack/commit/12fa19448594e1b3d54e68704f4d0d53c33e7e35))
* **ui:** Show release version in Control Panel and Info page header ([f4fe1e5](https://github.com/stefanko-ch/Nexus-Stack/commit/f4fe1e583050d5bf8797af5de938d5ee5df3dccd))
* **windmill:** Auto-configure workspace and secure default credentials ([cf5761e](https://github.com/stefanko-ch/Nexus-Stack/commit/cf5761ee09c8d35be5a5eeacda8ae40a899f35f3))


### 🐛 Bug Fixes

* Add --delete to rsync and guard empty Infisical token ([2b8e4dc](https://github.com/stefanko-ch/Nexus-Stack/commit/2b8e4dc35975239ea8e118af0f5d35b0652dcc6d))
* Add admin link to info panel and fix Filestash password ([45e712b](https://github.com/stefanko-ch/Nexus-Stack/commit/45e712b5243e0ce557c040be23d8396181d696a2))
* Add KV namespace binding to wrangler.toml for Pages deploy ([c4063b0](https://github.com/stefanko-ch/Nexus-Stack/commit/c4063b06b16f5b91d96672211efa295502b906ca))
* Address all PR review comments for Databricks sync ([41a3d68](https://github.com/stefanko-ch/Nexus-Stack/commit/41a3d68ebedadb4ef72ed8ad151a58e6ca5f4317))
* Address PR review - .netrc auth, idempotent .env, error logging ([cd6c05a](https://github.com/stefanko-ch/Nexus-Stack/commit/cd6c05ae21026c599748505b7abf91ff6ca94050))
* Address PR review — connection test, poll, and error handling ([10d9c6a](https://github.com/stefanko-ch/Nexus-Stack/commit/10d9c6acd97181e92073d2c3c9ff48ebc870e399))
* Address PR review — guard empty S3 secrets, default region ([524fd6b](https://github.com/stefanko-ch/Nexus-Stack/commit/524fd6be7aac763cf0360c4b9146960b4e44f925))
* Address PR review comments ([39b0766](https://github.com/stefanko-ch/Nexus-Stack/commit/39b076607e0ce1f4939877b624aa35608a3b2347))
* Address PR review comments for RisingWave stack ([0889d1a](https://github.com/stefanko-ch/Nexus-Stack/commit/0889d1adeb0bae8aca713672933ae3480d86440c))
* Address PR review comments from Copilot ([e302891](https://github.com/stefanko-ch/Nexus-Stack/commit/e3028911d907e2600cb963cccc426d4e5c689eeb))
* Address remaining PR review comments ([944d63c](https://github.com/stefanko-ch/Nexus-Stack/commit/944d63c058b2912e04b5c0fcbcb63e3d2ed9a686))
* Address second round of PR review comments ([036d7de](https://github.com/stefanko-ch/Nexus-Stack/commit/036d7de540f75fdf2b35ddeb0c9b93f70a40acc5))
* Address second round of PR review comments ([18818c3](https://github.com/stefanko-ch/Nexus-Stack/commit/18818c3c1671881d8b420fbfd2a6e08004f57641))
* **ci:** Add --region to all Hetzner S3 API calls ([fc66b3e](https://github.com/stefanko-ch/Nexus-Stack/commit/fc66b3e7b683e56b3084f58df93c35673bc151e6))
* **ci:** Add KV binding to spin-up Pages redeploy ([6759a70](https://github.com/stefanko-ch/Nexus-Stack/commit/6759a700cf5226e02c4173a937686325ede61287))
* **ci:** Add missing env vars to wrangler.toml for Pages Functions ([d8197d8](https://github.com/stefanko-ch/Nexus-Stack/commit/d8197d8b78a505f04afc43d3d100f20a1c943064))
* **ci:** add missing newline before persistent_volume_id in destroy-all ([4e58817](https://github.com/stefanko-ch/Nexus-Stack/commit/4e588179a4037cf2de8e777c65b2c56ef8a46a98))
* **ci:** Add pgducklake bucket to destroy & setup workflows ([31dc739](https://github.com/stefanko-ch/Nexus-Stack/commit/31dc73969c562cabc889d78148db0aa375230068))
* **ci:** Add retry for Cloudflare Pages deploy (504 timeouts) ([00d152a](https://github.com/stefanko-ch/Nexus-Stack/commit/00d152a43bffe8aade32501a78ce5fdbeeafbee7))
* **ci:** Add retry logic for Cloudflare Pages deploy (504 timeouts) ([bc64413](https://github.com/stefanko-ch/Nexus-Stack/commit/bc64413c539e54d154879e8781fb76d5edb4f495))
* **ci:** Address PR [#404](https://github.com/stefanko-ch/Nexus-Stack/issues/404) review feedback ([06e6043](https://github.com/stefanko-ch/Nexus-Stack/commit/06e60438aed404aa6c2f1d8b84edd9d8a3ee1d21))
* **ci:** Address PR [#405](https://github.com/stefanko-ch/Nexus-Stack/issues/405) review feedback - add permissions block and sync guard ([f8d76f0](https://github.com/stefanko-ch/Nexus-Stack/commit/f8d76f0e5cac3342d3b96921a32f694e73fb9f95))
* **ci:** Address PR review comments ([39a2263](https://github.com/stefanko-ch/Nexus-Stack/commit/39a2263446f01d0eb4025ddcf695020da03ab720))
* **ci:** Address PR review comments for persistent_volume_id validation ([6aa63db](https://github.com/stefanko-ch/Nexus-Stack/commit/6aa63db326e80395a47f2fee007a94acbf75f9c0))
* **ci:** Address PR review comments for R2 token cleanup ([9a6d441](https://github.com/stefanko-ch/Nexus-Stack/commit/9a6d441ca3363d3f0cb31e6795faadc7956e34e2))
* **ci:** Change default server location back to fsn1 ([4c3406a](https://github.com/stefanko-ch/Nexus-Stack/commit/4c3406aacbcf7340c07eda34017a6198e8baca1f))
* **ci:** Delete R2 bucket before revoking R2 API token ([08dca5b](https://github.com/stefanko-ch/Nexus-Stack/commit/08dca5bf8eabe173307cff3c3a588f6993b7a339))
* **ci:** Derive Object Storage region from server hostname ([74fd3ed](https://github.com/stefanko-ch/Nexus-Stack/commit/74fd3edc1f683a1f3ff954acfb2d5b41f5886fc7))
* **ci:** Ensure R2 state bucket exists before tofu init and harden error handling ([1b0a3c7](https://github.com/stefanko-ch/Nexus-Stack/commit/1b0a3c7030d58fe2e9fd802608a6d8ade771fba8))
* **ci:** fix heredoc indentation corrupting R2 credentials and config files ([88b5666](https://github.com/stefanko-ch/Nexus-Stack/commit/88b5666bbfd3743f12975403ca859ea403f8cbb2))
* **ci:** Fix worker secret conflicts and R2 credential error handling ([788be31](https://github.com/stefanko-ch/Nexus-Stack/commit/788be3119541f4109dcb1d798f4ebafd7e20c159))
* **ci:** Fix worker secret conflicts and R2 credential error handling ([f296e5c](https://github.com/stefanko-ch/Nexus-Stack/commit/f296e5c85eca56165da375dda2e4c146a2177b04)), closes [#279](https://github.com/stefanko-ch/Nexus-Stack/issues/279) [#280](https://github.com/stefanko-ch/Nexus-Stack/issues/280)
* **ci:** Gracefully handle missing R2 credentials in destroy-all ([9503182](https://github.com/stefanko-ch/Nexus-Stack/commit/950318229a1821b0954154055d0217773f79af18))
* **ci:** Handle R2 credential validation failure gracefully ([e6935c8](https://github.com/stefanko-ch/Nexus-Stack/commit/e6935c81d1d22dbaa1c85f8b810f273f13e4309a))
* **ci:** Handle tainted Hetzner buckets in cleanup step ([22dd450](https://github.com/stefanko-ch/Nexus-Stack/commit/22dd45018279498a01b22375aef9bacfb92b4d10))
* **ci:** Import existing S3 buckets instead of deleting them ([1e9c803](https://github.com/stefanko-ch/Nexus-Stack/commit/1e9c8036194d2ff5ab89d20ace75bdf009d17d28))
* **ci:** Improve Hetzner S3 bucket cleanup in destroy-all workflow ([bc6b630](https://github.com/stefanko-ch/Nexus-Stack/commit/bc6b63073d20e60969020fe9a340794964c2b683))
* **ci:** indent heredoc content and strip with sed to prevent YAML corruption ([97e426f](https://github.com/stefanko-ch/Nexus-Stack/commit/97e426f4f119a99e6a9f145d9e0dcf65177538b8))
* **ci:** Init both control-plane and stack state in databricks-sync ([7284e67](https://github.com/stefanko-ch/Nexus-Stack/commit/7284e6743108aadd506f8dcb362268a28e62b67e))
* **ci:** Keep R2 state credentials across destroy-all ([052fa46](https://github.com/stefanko-ch/Nexus-Stack/commit/052fa4644ab13ea0530b15f4a2268e7383210ce3))
* **ci:** Make Hetzner Object Storage non-blocking in setup workflow ([2785b3a](https://github.com/stefanko-ch/Nexus-Stack/commit/2785b3a14c10af74b64b3bef771d2e34b7705686))
* **ci:** Make Hetzner region configurable via SERVER_LOCATION variable ([91d88f9](https://github.com/stefanko-ch/Nexus-Stack/commit/91d88f9cbfa57601205b01b4d2574fd11bdda1cc)), closes [#278](https://github.com/stefanko-ch/Nexus-Stack/issues/278)
* **ci:** Make Hetzner server region configurable via repository variable ([b57fdc4](https://github.com/stefanko-ch/Nexus-Stack/commit/b57fdc4134c1c9bdaba6bc344b65995705f8e095))
* **ci:** mask SSH private key in logs and harden file creation ([d668378](https://github.com/stefanko-ch/Nexus-Stack/commit/d66837894bfa6ecf14f426dc9581ef298653e2e1))
* **ci:** pass SSH private key as workflow output for initial setup ([69d433e](https://github.com/stefanko-ch/Nexus-Stack/commit/69d433ef33500d7289ce305289271dd7d15c7225))
* **ci:** pass SSH private key as workflow output for initial setup ([b7a30a1](https://github.com/stefanko-ch/Nexus-Stack/commit/b7a30a143c848be089b785e2e86e4a103d465d18))
* **ci:** Pin Node.js 22 in setup-control-plane and spin-up workflows ([438d71a](https://github.com/stefanko-ch/Nexus-Stack/commit/438d71a1f050beca05c034119e8c2bbcaf555bd1))
* **ci:** Pin wrangler to [@4](https://github.com/4) instead of [@latest](https://github.com/latest) ([247cdf8](https://github.com/stefanko-ch/Nexus-Stack/commit/247cdf8ee0e60bf080044572123ea79549ec1b70))
* **ci:** Pin wrangler to major version 4 instead of [@latest](https://github.com/latest) ([962495e](https://github.com/stefanko-ch/Nexus-Stack/commit/962495e67356bac91f424bdb0cc191efe351f03c))
* **ci:** Place shellcheck disable directly before each ssh line ([b5f2854](https://github.com/stefanko-ch/Nexus-Stack/commit/b5f28547051518bbbb51fb9d48161e62694c1c71))
* **ci:** Pre-create Hetzner S3 buckets to avoid provider ACL error ([d716ffe](https://github.com/stefanko-ch/Nexus-Stack/commit/d716ffe01a2e762299d2e5de2383efaaed421784))
* **ci:** Preserve R2 state bucket across destroy-all ([09aceec](https://github.com/stefanko-ch/Nexus-Stack/commit/09aceeca8f78bc15e9314731a8b981f575acb7c5))
* **ci:** Prevent set -e from killing script on aws bucket creation failure ([9fb9c75](https://github.com/stefanko-ch/Nexus-Stack/commit/9fb9c754a36514730d36ac81f3c71f1139c81279))
* **ci:** Propagate HETZNER_S3_LOCATION to OpenTofu variables ([b0575dc](https://github.com/stefanko-ch/Nexus-Stack/commit/b0575dc98497cc33b5b718d133f9b22c9bc7f877))
* **ci:** Read both Infisical token and project ID from server via SSH before port closes ([9c98665](https://github.com/stefanko-ch/Nexus-Stack/commit/9c986656d4d3e284bea2e49be465cec7d7f9516c))
* **ci:** Read Infisical project ID before SSH port closes, use job-level token var ([1edd07c](https://github.com/stefanko-ch/Nexus-Stack/commit/1edd07c6d59b0bc465f9699bcdfdb3633399e40a))
* **ci:** remove empty expression placeholder from comment ([03b347d](https://github.com/stefanko-ch/Nexus-Stack/commit/03b347d90dc5fdc7b592a05c311070a9754d17cf))
* **ci:** remove SSH key masking that corrupts R2 credentials ([1b545ca](https://github.com/stefanko-ch/Nexus-Stack/commit/1b545ca7c49901cc95e7ab9c395d2e3398b725df))
* **ci:** remove SSH key masking that corrupts R2 credentials ([89e7b57](https://github.com/stefanko-ch/Nexus-Stack/commit/89e7b5736a26bd8ba84798f88b2be4276ce45c1b))
* **ci:** Remove stale .r2-credentials before recreating R2 token ([43e9bd5](https://github.com/stefanko-ch/Nexus-Stack/commit/43e9bd50ba67debce0713f75694a1f7970f04fe7))
* **ci:** Remove unused BUCKET_NAME variable in R2 validation ([3cd872a](https://github.com/stefanko-ch/Nexus-Stack/commit/3cd872ab0ad8a525fdcdb17f9a0ae817118c0138))
* **ci:** Replace A && B || C pattern with proper if-else ([eaa5ff4](https://github.com/stefanko-ch/Nexus-Stack/commit/eaa5ff42dce953598bc4b297f92b4cde297dc249))
* **ci:** replace useless cat with input redirection (SC2002) ([2e673e6](https://github.com/stefanko-ch/Nexus-Stack/commit/2e673e6d7a57c97e1173ad520fe5c276b6faf67a))
* **ci:** Restore Pages env vars via API after wrangler deploy ([b4ed393](https://github.com/stefanko-ch/Nexus-Stack/commit/b4ed3938a13618bec1d7f1be79cd671318cade9c))
* **ci:** Restore Pages secrets for GITHUB_OWNER, GITHUB_REPO and other vars ([953fb35](https://github.com/stefanko-ch/Nexus-Stack/commit/953fb356799944e561bff6ad9a35736a22458828))
* **ci:** restore SSH key heredoc indentation for YAML parser compatibility ([f4dbfd0](https://github.com/stefanko-ch/Nexus-Stack/commit/f4dbfd0ecf3c899ffc99811808b3b3feedf380e5))
* **ci:** Reword fork safety comment to reflect actual gate ([eb32494](https://github.com/stefanko-ch/Nexus-Stack/commit/eb3249445d24f36eb70c81f3ea9b717b3dd7e2a0))
* **ci:** Scope R2 token deletion to own deployment only ([1b43e05](https://github.com/stefanko-ch/Nexus-Stack/commit/1b43e051437ad363e3496a540b8da0e854d10641))
* **ci:** Scope R2 token deletion to own deployment only ([a87d3b9](https://github.com/stefanko-ch/Nexus-Stack/commit/a87d3b9644264d0f930070e74dc322fed1fd4e1c))
* **ci:** Separate Object Storage region from server location ([814f24c](https://github.com/stefanko-ch/Nexus-Stack/commit/814f24cbd7755b1cb3815ca84d60708e442cf039))
* **ci:** Separate R2 and Hetzner credentials in bucket cleanup step ([67b7506](https://github.com/stefanko-ch/Nexus-Stack/commit/67b750686f543926675841db0e14966fcbe7c1a9))
* **ci:** Show actual error when bucket pre-creation fails ([7c42343](https://github.com/stefanko-ch/Nexus-Stack/commit/7c42343016485a807c6ca5638a0da64e65388214))
* **ci:** Stop swallowing tofu init errors in destroy workflow ([6f1bf2c](https://github.com/stefanko-ch/Nexus-Stack/commit/6f1bf2c185e01e22851d7e9c09a954ff61055bde))
* **ci:** Suppress SC2029 in databricks-sync (intentional local expansion) ([2d61b92](https://github.com/stefanko-ch/Nexus-Stack/commit/2d61b922ef014bee67ed8f03bdee7ce2a78676fc))
* **ci:** Suppress shellcheck warnings in databricks-sync workflow ([cc0665e](https://github.com/stefanko-ch/Nexus-Stack/commit/cc0665e9caa806a62f084c9ec9f3f70c60ac1cc4))
* **ci:** Switch docs sync from repository_dispatch to Cloudflare Deploy Hook ([fe35c0e](https://github.com/stefanko-ch/Nexus-Stack/commit/fe35c0e3e7ff6afd004a697382874a47d471e578))
* **ci:** Switch docs sync to Cloudflare Deploy Hook ([a88c2ff](https://github.com/stefanko-ch/Nexus-Stack/commit/a88c2ff6eac8c87fbd1bdac5af1e4c978dd8546d))
* **ci:** Update spin-up workflow for Astro build (control-plane/pages removed) ([b088ec0](https://github.com/stefanko-ch/Nexus-Stack/commit/b088ec0656462657c7e99150d89ab86ff23f8f5d))
* **ci:** Upgrade setup-node v5, fix Hetzner Object Storage resilience ([9970c92](https://github.com/stefanko-ch/Nexus-Stack/commit/9970c92fcb472ed8ab182f9ea47c72b9e1cbf1c3))
* **ci:** Use accountID/namespaceID format for KV import ([38af6b4](https://github.com/stefanko-ch/Nexus-Stack/commit/38af6b4618a513053154199946bba0ac538c614f))
* **ci:** Use accountID/namespaceID format for KV import ([2cbc3c0](https://github.com/stefanko-ch/Nexus-Stack/commit/2cbc3c0ad16f7a5ef46fc4244a4fd888ca0f7c78))
* **ci:** Use dynamic worker name and remove unused wrangler.toml ([98c1bb3](https://github.com/stefanko-ch/Nexus-Stack/commit/98c1bb36bd8009258be480d52e3bf06cdef19ff3))
* **ci:** Use env var for secrets check in step conditions (actionlint) ([5ab83b5](https://github.com/stefanko-ch/Nexus-Stack/commit/5ab83b5a5cfbf824558d97d3ef053f3e1aaae1d0))
* **ci:** use indented heredocs with sed strip for YAML parser compatibility ([d3fbe26](https://github.com/stefanko-ch/Nexus-Stack/commit/d3fbe26453be9a161a442f02a7e2182ba7d803fd))
* **ci:** Validate numeric IDs in Close SSH port step ([b910c75](https://github.com/stefanko-ch/Nexus-Stack/commit/b910c75a37dfaedbb839ad679e7254dae403f0bf))
* **ci:** Validate persistent_volume_id before writing to tfvars ([00cb8c2](https://github.com/stefanko-ch/Nexus-Stack/commit/00cb8c2d00ab1b12f7287f377be6144c7bc0f4c1))
* **ci:** Validate persistent_volume_id before writing to tfvars ([37795f8](https://github.com/stefanko-ch/Nexus-Stack/commit/37795f8321b1f93da1d0856384516240bef52ec6))
* **ci:** Validate R2 credentials before use, auto-recreate if invalid ([7918854](https://github.com/stefanko-ch/Nexus-Stack/commit/7918854636b0ad5de93442e6b07a2dc821112b76))
* **control-plane:** Add D1 logging to 5 unlogged API endpoints ([a21d8db](https://github.com/stefanko-ch/Nexus-Stack/commit/a21d8db6fd8d26aca163d01cd15c4af67527071b))
* **control-plane:** Address Copilot review comments on email-settings API ([e596176](https://github.com/stefanko-ch/Nexus-Stack/commit/e596176487e101407590f03ed93a6f0c41f02913))
* **control-plane:** Address PR [#341](https://github.com/stefanko-ch/Nexus-Stack/issues/341) review feedback ([8459409](https://github.com/stefanko-ch/Nexus-Stack/commit/84594099101c733bff9b16601fd0b1a7cdd7894c))
* **control-plane:** Address PR [#402](https://github.com/stefanko-ch/Nexus-Stack/issues/402) review feedback ([c1fc22d](https://github.com/stefanko-ch/Nexus-Stack/commit/c1fc22d122d09a7ff121fc7a47d77a5124bd95fd))
* **control-plane:** Address PR review - restore CF-Access auth check, use env for Infisical env, surface warnings ([513954b](https://github.com/stefanko-ch/Nexus-Stack/commit/513954bd697213ad845cb42d989100dea6729924))
* **control-plane:** Address PR review comments ([3da99ee](https://github.com/stefanko-ch/Nexus-Stack/commit/3da99eeb20625661a18ad00c12dfd140e295b798))
* **control-plane:** Address PR review comments for XSS, auth, and cleanup ([efb3457](https://github.com/stefanko-ch/Nexus-Stack/commit/efb34574b873936152ac1624bfe68f16e046d901))
* **control-plane:** Destructure request from context in services API ([81dc49e](https://github.com/stefanko-ch/Nexus-Stack/commit/81dc49eb79cde53661723232021417d80cf4e23e))
* **control-plane:** Enable workers.dev subdomain via API instead of TF resource ([4122176](https://github.com/stefanko-ch/Nexus-Stack/commit/4122176ba3c8b5773b8cb73a3033c8e506f24b6b))
* **control-plane:** Fix pending changes race condition and improve UX ([63fdbb0](https://github.com/stefanko-ch/Nexus-Stack/commit/63fdbb08f8cbdbed091dd5d6383393052b71b32a))
* **control-plane:** Fix pending changes UX and CI error handling ([280b243](https://github.com/stefanko-ch/Nexus-Stack/commit/280b2432ddbe7e6d99dd46f49be5c00c86fb4595))
* **control-plane:** Fix Secrets page by adding CF Access Service Token for Infisical API ([3318059](https://github.com/stefanko-ch/Nexus-Stack/commit/331805984c774b36618807e73504dcdc327912b2))
* **control-plane:** Fix settings.html API response parsing ([92e75d1](https://github.com/stefanko-ch/Nexus-Stack/commit/92e75d1bddd5321d0ee1b9e48472a23f54574d09))
* **control-plane:** Fix stack chips styling with :global for dynamic elements ([77d6065](https://github.com/stefanko-ch/Nexus-Stack/commit/77d6065ad2d194e768e330f2d0c130ce0df67b24))
* **control-plane:** Guard removed DOM elements and remove stale init calls ([a1edd09](https://github.com/stefanko-ch/Nexus-Stack/commit/a1edd09f4ceda02df5f4098af06b59ae32125adc))
* **control-plane:** Pin wrangler@4 for pages secret put, rename root secrets group to avoid collision ([4b40565](https://github.com/stefanko-ch/Nexus-Stack/commit/4b40565ecfb3cc85cfbc431099d47a3be80bbc49))
* **control-plane:** Redesign active stacks as clickable chip buttons ([780e5ae](https://github.com/stefanko-ch/Nexus-Stack/commit/780e5aeac4a8f9a3f2d29428ff1dca9ad0a7bcd1))
* **control-plane:** Remove all dead JS functions and event listeners ([6eef679](https://github.com/stefanko-ch/Nexus-Stack/commit/6eef679a1039ad554d6f06b0ae13e126378229ac))
* **control-plane:** Remove CF-Access header check that breaks Pages Functions ([af94a06](https://github.com/stefanko-ch/Nexus-Stack/commit/af94a064790aecf2d6a4c232a6ebf46ec8cf98f3))
* **control-plane:** Remove strict CF-Access header check on secrets API, fix search dropdown styles ([c52ba61](https://github.com/stefanko-ch/Nexus-Stack/commit/c52ba610e9046ecc74fb99116a446a910c572129))
* **control-plane:** Return 'destroyed' instead of 'offline' from status API ([37d78ee](https://github.com/stefanko-ch/Nexus-Stack/commit/37d78eef98113d3df62da771edbf39ab92276266))
* **control-plane:** Stack chips as vertical list in boxes ([2d09783](https://github.com/stefanko-ch/Nexus-Stack/commit/2d0978397c6a144f914f3e15c1501799dbf1ab84))
* **control-plane:** Use arrayBuffer for byte-accurate body size check ([7416e4a](https://github.com/stefanko-ch/Nexus-Stack/commit/7416e4a54c51f94189126713c39ebb0608cb2dd9))
* **control-plane:** use European date format in logs page ([8457c15](https://github.com/stefanko-ch/Nexus-Stack/commit/8457c158e1e6c1190ed73540613508f78515d10d))
* Databricks sync fixes, connection test, and status polling ([f724f2a](https://github.com/stefanko-ch/Nexus-Stack/commit/f724f2a794040892c26fd1c860f36e7cf42e0ba8))
* **deploy:** Follow-up security and error handling improvements ([#179](https://github.com/stefanko-ch/Nexus-Stack/issues/179)) ([100de11](https://github.com/stefanko-ch/Nexus-Stack/commit/100de111b42ef9f83baffaac390885a807a282d6))
* **docs:** Add missing Draw.io documentation and README entry ([91c8867](https://github.com/stefanko-ch/Nexus-Stack/commit/91c8867ae20c533465b96fb8cc4b69fb6a64720c))
* **docs:** Add pg-ducklake to overview, fix Swiss capitalization ([3c4178a](https://github.com/stefanko-ch/Nexus-Stack/commit/3c4178ab9d59ca341f55eb511d6491eac3fa16d3))
* **docs:** Address PR [#223](https://github.com/stefanko-ch/Nexus-Stack/issues/223) review comments ([0965be7](https://github.com/stefanko-ch/Nexus-Stack/commit/0965be73b1f956ad5cb119d893a33cc4696e2527))
* **docs:** Address PR [#405](https://github.com/stefanko-ch/Nexus-Stack/issues/405) review feedback - sync guard docs and stack count ([a936c91](https://github.com/stefanko-ch/Nexus-Stack/commit/a936c91531b2ef592b6d59e0f23fb1401c4f0f5f))
* **docs:** Address PR [#405](https://github.com/stefanko-ch/Nexus-Stack/issues/405) review feedback - token guard and security text ([3e6a78c](https://github.com/stefanko-ch/Nexus-Stack/commit/3e6a78c4b25c2ab7c08a171935e2931fa93d054d))
* **docs:** Address PR [#406](https://github.com/stefanko-ch/Nexus-Stack/issues/406) review feedback ([56801a1](https://github.com/stefanko-ch/Nexus-Stack/commit/56801a12cdd9b3c3fb81c8546cb19eb97541f540))
* **docs:** Address PR [#406](https://github.com/stefanko-ch/Nexus-Stack/issues/406) review feedback - fail on missing hook, fix docs ([fe188e9](https://github.com/stefanko-ch/Nexus-Stack/commit/fe188e9673211593896be187cbb93b8ac2432be9))
* **docs:** Align AKHQ version strategy and description ([f8d78dd](https://github.com/stefanko-ch/Nexus-Stack/commit/f8d78dd72510fa0441e5598fbc29ad0daae8f46d))
* **docs:** Align Debezium docs with internal_only access model ([54a928e](https://github.com/stefanko-ch/Nexus-Stack/commit/54a928e4b73e6484f60615600932e3d172b7d411))
* **docs:** Change Soda badge logo from 'soda' to 'database' ([1e905bc](https://github.com/stefanko-ch/Nexus-Stack/commit/1e905bcb1c89de9f5d39c78e64c3f37535cf166f))
* **docs:** Correct footnote and Dinky resource limits ([e4cf353](https://github.com/stefanko-ch/Nexus-Stack/commit/e4cf35311e612cfadfea02833ece25a9f21ef587))
* **docs:** Move bluesky-flink-tutorial from stacks/ to tutorials/ ([d3276c3](https://github.com/stefanko-ch/Nexus-Stack/commit/d3276c3bb397ee9af4566dcad98e5ca2618ecafc))
* **docs:** Redesign architecture SVG with cleaner layout ([854b1d3](https://github.com/stefanko-ch/Nexus-Stack/commit/854b1d3c0c69b55b1017b54716a2be60d7c2e85f))
* Merge read+push steps (trap EXIT deleted file) and use 24h time ([2ba10f0](https://github.com/stefanko-ch/Nexus-Stack/commit/2ba10f09137a671237ae33ec23e6cf39c64e69da))
* Only retry on 504 timeouts, use ISO timestamp for sync status ([253fb62](https://github.com/stefanko-ch/Nexus-Stack/commit/253fb620a43bffd5a4f92c9aa3ed865d8c3657ac))
* Pass R2 data credentials from setup to spin-up for first-run ([b21722e](https://github.com/stefanko-ch/Nexus-Stack/commit/b21722ea9424d7cb39a010fc8bb48ccce51d3fd0))
* **prefect:** Add PREFECT_API_URL to prefect-services container ([d889db9](https://github.com/stefanko-ch/Nexus-Stack/commit/d889db9e68529fd73000bd5373e79882382a5b12))
* Protect persistent volume from destroy-all ([6a40dad](https://github.com/stefanko-ch/Nexus-Stack/commit/6a40dadab1cd04bf41561adee3bf2392d1976368))
* Protect S3 buckets from destroy-all and use single Databricks scope ([8fb7625](https://github.com/stefanko-ch/Nexus-Stack/commit/8fb762513967f744fd5e8480295612735743f25e))
* Protect S3 buckets from destroy-all, single Databricks scope ([5000b53](https://github.com/stefanko-ch/Nexus-Stack/commit/5000b53eebe2a649c3c2283c16285b60d2394678))
* Read secrets from OpenTofu state for Databricks sync ([d083b5f](https://github.com/stefanko-ch/Nexus-Stack/commit/d083b5f9178cbd66fb0639f28f274c8e4a9c885d))
* Read secrets from OpenTofu state instead of Infisical API ([019bfc0](https://github.com/stefanko-ch/Nexus-Stack/commit/019bfc0ed8721977b9381cc70dd2809b17219761))
* Remove secret values from debug output, show only keys/count ([0574000](https://github.com/stefanko-ch/Nexus-Stack/commit/0574000aa4b4a8a2ea6187500e02e2bb3262b2cd))
* Rename hetzner_s3_bucket to hetzner_s3_bucket_lakefs in secrets output ([68fff6b](https://github.com/stefanko-ch/Nexus-Stack/commit/68fff6b0105b6b03d5695b5675c68a7eb7a67686))
* **scripts:** Add NocoDB JWT secret to Infisical and validate .env generation ([3543c91](https://github.com/stefanko-ch/Nexus-Stack/commit/3543c91aa51bbe4e0efcaa15401ac1db1149c6e7))
* **scripts:** address PR review feedback for SSH error debugging ([95fb101](https://github.com/stefanko-ch/Nexus-Stack/commit/95fb101aee15c266b268c204785585176774816b))
* **scripts:** Base64 encode passwords for OpenMetadata API ([fddde25](https://github.com/stefanko-ch/Nexus-Stack/commit/fddde25cddbfd4e525d57df7e478639ea5ef82cd))
* **scripts:** Define OM_PRINCIPAL_DOMAIN unconditionally in deploy.sh ([a840427](https://github.com/stefanko-ch/Nexus-Stack/commit/a840427da876f6b2a97b20882df435cee53f821c))
* **scripts:** Fix Dify auto-setup and storage permissions ([3e57ab4](https://github.com/stefanko-ch/Nexus-Stack/commit/3e57ab40d91e62e9f951b04e76932e34d7d566a3))
* **scripts:** Fix Infisical secrets push JSON parse error ([9b89c4a](https://github.com/stefanko-ch/Nexus-Stack/commit/9b89c4accc91541deb3faa605137e40473c28f1e))
* **scripts:** Fix invalid JSON in Infisical secrets payload ([04bf37b](https://github.com/stefanko-ch/Nexus-Stack/commit/04bf37b7c283b6d60b7aaec109935f77f85ad984))
* **scripts:** Fix variable expansion for Dify storage chown ([c6cf877](https://github.com/stefanko-ch/Nexus-Stack/commit/c6cf8770cc82c1ad3632b398fa3be67dc8a6cc91))
* **scripts:** Remove duplicate OM_PRINCIPAL_DOMAIN definition ([051fee7](https://github.com/stefanko-ch/Nexus-Stack/commit/051fee7a4d99c028c710fd5f7aca0073e0f7b734))
* **scripts:** Require full S3 var set before generating pg_ducklake S3 secret ([c14c09e](https://github.com/stefanko-ch/Nexus-Stack/commit/c14c09eab0a99df5c50b08dc6508cef87ce82a0f))
* **scripts:** Require special chars in OpenMetadata admin password ([b13849c](https://github.com/stefanko-ch/Nexus-Stack/commit/b13849c825d506874f5503f1ee3962cb4b602073))
* **scripts:** Restore LOG_FILE variable used by debug logging ([a3ca51f](https://github.com/stefanko-ch/Nexus-Stack/commit/a3ca51f8bede2b33f708aaf4e6dda3aad7475f97))
* **scripts:** show SSH errors instead of suppressing with 2&gt;/dev/null ([d92bb23](https://github.com/stefanko-ch/Nexus-Stack/commit/d92bb235fee2abd424eab77c7b3a4d8f0f30dc30))
* **scripts:** show SSH errors instead of suppressing with 2&gt;/dev/null ([f12bc60](https://github.com/stefanko-ch/Nexus-Stack/commit/f12bc605650746db3dafe8207ed2cc8680ccd4e3))
* **scripts:** Use correct Infisical v3 batch API endpoint ([a7e28a6](https://github.com/stefanko-ch/Nexus-Stack/commit/a7e28a65cb673a5e94bc351748e1eb5f27527c73))
* **scripts:** Use correct OpenMetadata password change endpoint ([99eb970](https://github.com/stefanko-ch/Nexus-Stack/commit/99eb9707da06a0da18df09cb9c2dd9a039df3ed4))
* **scripts:** Use curl -s instead of curl -sf for Gitea API calls ([086cbcf](https://github.com/stefanko-ch/Nexus-Stack/commit/086cbcf5b695839c7c7da87fb676f38b067c68c4))
* **scripts:** Use domain-based R2 API token naming for multi-user safety ([dcfad69](https://github.com/stefanko-ch/Nexus-Stack/commit/dcfad694eeb04bb4e710b8c3d019bf6015b260de))
* **scripts:** Use plain text passwords for OpenMetadata password change API ([795fcc3](https://github.com/stefanko-ch/Nexus-Stack/commit/795fcc3927d33885a89bbf1ad0bd850138098d34))
* Secure temp file permissions and use printf for secret values ([bc3a239](https://github.com/stefanko-ch/Nexus-Stack/commit/bc3a2397cc748aca6565de9ff4564d9f463e6597))
* skip scheduled teardown when infrastructure is not deployed ([23aae1b](https://github.com/stefanko-ch/Nexus-Stack/commit/23aae1bc9079929c3c44cef4d5e3d4200ca07f80))
* Skip sleep after final retry attempt, fix deploy log messages ([3e77a0c](https://github.com/stefanko-ch/Nexus-Stack/commit/3e77a0c8bda6bc9c692de73e3437646566e3ac99))
* **soda:** Add ARM64 support with custom Dockerfile ([37836f5](https://github.com/stefanko-ch/Nexus-Stack/commit/37836f56e425ecfde19cbd926ad0ac3bace8c33a))
* Stability overhaul across infrastructure, workflows, and Docker stacks ([12f7847](https://github.com/stefanko-ch/Nexus-Stack/commit/12f78474282a3db6014d571b8a1c0e0384da7a6f))
* Stability overhaul across infrastructure, workflows, and Docker stacks ([6b359e7](https://github.com/stefanko-ch/Nexus-Stack/commit/6b359e7fcfa051832e5ab7b083fac1fc1094f3d4))
* **stacks:** Add env_file and anonymous access to CloudBeaver ([7da00f2](https://github.com/stefanko-ch/Nexus-Stack/commit/7da00f21d7b539b834d06bce89b35ed18896fdca))
* **stacks:** Add hadoop-aws and AWS SDK v2 JARs for S3A support ([bd0d80c](https://github.com/stefanko-ch/Nexus-Stack/commit/bd0d80c08458df4889804cb9199e9fa50f3aea67))
* **stacks:** add INSTALL_LOCK to Gitea to skip web installer ([c07c0b5](https://github.com/stefanko-ch/Nexus-Stack/commit/c07c0b5fd18ac4e350e84e9158fa0fa0f7e5b1b8))
* **stacks:** Add missing plugin daemon env vars and nginx depends_on ([48d7f86](https://github.com/stefanko-ch/Nexus-Stack/commit/48d7f86b7683c6d196d16139134acffd07ab1d59))
* **stacks:** Add MySQL JDBC driver to Dinky for persistent catalog ([399b53c](https://github.com/stefanko-ch/Nexus-Stack/commit/399b53c81b96313d586a14c55a24dc768b3dd93a))
* **stacks:** Add password reset on Superset startup to fix Invalid login ([33f1713](https://github.com/stefanko-ch/Nexus-Stack/commit/33f1713931e786575b73d60a28b0e6c76026b105))
* **stacks:** Add PYTHONPATH for PySpark in Jupyter container ([513b12e](https://github.com/stefanko-ch/Nexus-Stack/commit/513b12e46bf9c04d28b24eea9718437f231fad8b))
* **stacks:** Add Redis config to Dify plugin daemon ([08de791](https://github.com/stefanko-ch/Nexus-Stack/commit/08de7910eba8d9c0d5a8ef7c4e755b85d1735ea5))
* **stacks:** Address Appsmith PR review feedback ([6775d2e](https://github.com/stefanko-ch/Nexus-Stack/commit/6775d2e474673163e0ae52851e934aee0b844c46))
* **stacks:** Address Debezium PR review comments ([efdb14d](https://github.com/stefanko-ch/Nexus-Stack/commit/efdb14df13f49dc2a2f1db960e9d78a5a6071e09))
* **stacks:** Address PR review — pin versions, restore image override ([bfcb46b](https://github.com/stefanko-ch/Nexus-Stack/commit/bfcb46b8829d97a21cadef393a3439fc8b6837b8))
* **stacks:** Address PR review comments ([e3f7f1d](https://github.com/stefanko-ch/Nexus-Stack/commit/e3f7f1d0a051ae80b5979ed0de9e859b54a62064))
* **stacks:** Address PR review comments for Dify stack ([4d4857e](https://github.com/stefanko-ch/Nexus-Stack/commit/4d4857e148f2922853bfa0f3170a341feb9ed7db))
* **stacks:** Address PR review comments for Dinky ([4664c66](https://github.com/stefanko-ch/Nexus-Stack/commit/4664c66e9107ee6743f72094e66edf1d1f16df3f))
* **stacks:** Address PR review comments for mirror feature ([e08c1b6](https://github.com/stefanko-ch/Nexus-Stack/commit/e08c1b638b3639faf78974e2317cd035f10395c6))
* **stacks:** Address PR review comments for Quickwit and NocoDB ([1f431a4](https://github.com/stefanko-ch/Nexus-Stack/commit/1f431a4f106dac4212172327761e674151b66a23))
* **stacks:** Address PR review comments for Spark stack ([038f75e](https://github.com/stefanko-ch/Nexus-Stack/commit/038f75ecad92c957e89798badfe2dd77e7abf033))
* **stacks:** Address PR review comments for Woodpecker stack ([8bc9b29](https://github.com/stefanko-ch/Nexus-Stack/commit/8bc9b29bfd58429de5acbc195f58a7830c8d2fdb))
* **stacks:** Address Sling PR review comments ([6c4df8c](https://github.com/stefanko-ch/Nexus-Stack/commit/6c4df8c83e9185e630968342506360b808c3573a))
* **stacks:** Address Superset PR review - isolate create-admin failure, push all secrets to Infisical ([82b8ff0](https://github.com/stefanko-ch/Nexus-Stack/commit/82b8ff0531a1e18b9ae18ab65cd001888f398efc))
* **stacks:** address Trino PR review feedback ([d1ba85e](https://github.com/stefanko-ch/Nexus-Stack/commit/d1ba85e2656e715d190619bfd2616310b227d360))
* **stacks:** Address Vector/Telegraf PR review comments ([7e217e1](https://github.com/stefanko-ch/Nexus-Stack/commit/7e217e139670570dc1e642dfd8a74065b6ee1f96))
* **stacks:** allow forwarded headers in Trino for Cloudflare Tunnel ([11cffec](https://github.com/stefanko-ch/Nexus-Stack/commit/11cffec423873246b22552e2431939f7012fb420))
* **stacks:** Always overwrite starter notebook on Jupyter startup ([82746d2](https://github.com/stefanko-ch/Nexus-Stack/commit/82746d2917c8522634445d7118de35f7c54be3d8))
* **stacks:** Auto-configure CloudBeaver to skip initial setup wizard ([dc5b549](https://github.com/stefanko-ch/Nexus-Stack/commit/dc5b5490d94b0a39f984fccd8e180c42e124f583))
* **stacks:** Bind Spark master/worker to all network interfaces ([d444854](https://github.com/stefanko-ch/Nexus-Stack/commit/d444854fb6413bb5e652d6df27111e892f4a6a07))
* **stacks:** Build custom Spark image with Python 3.13 to match Jupyter ([2368667](https://github.com/stefanko-ch/Nexus-Stack/commit/2368667d2b163e08be24cc51ac41d679aa42f801))
* **stacks:** Complete Quickwit and NocoDB integration ([9915326](https://github.com/stefanko-ch/Nexus-Stack/commit/991532698b64984f805a30e96d4c923e7535649a))
* **stacks:** Connect RisingWave dashboard to Prometheus ([e3e4ca1](https://github.com/stefanko-ch/Nexus-Stack/commit/e3e4ca1b6fab1176772fd04e830e25abbb2e496a))
* **stacks:** correct ClickHouse image tag to 25.8.16.34 ([e448cef](https://github.com/stefanko-ch/Nexus-Stack/commit/e448cef667f7ea08db167e1f50090a608fbb1b39))
* **stacks:** Disable auth for code-server and Jupyter, pin image versions ([5edb80b](https://github.com/stefanko-ch/Nexus-Stack/commit/5edb80ba44fd22ab0a2cf7a163379704941fb762))
* **stacks:** Disable Marimo access token (behind Cloudflare Access) ([9035e77](https://github.com/stefanko-ch/Nexus-Stack/commit/9035e7750297580d4c68b8f5b5c2acc60e9bd473))
* **stacks:** Disable must-change-password on Gitea password sync ([1c7c661](https://github.com/stefanko-ch/Nexus-Stack/commit/1c7c661cfdd64f9e1c90d069b9ce713723f18cac))
* **stacks:** Enable Dify database migrations on startup ([68c32b4](https://github.com/stefanko-ch/Nexus-Stack/commit/68c32b4ee7b9ac668d555746368bd498cd674fd5))
* **stacks:** Fix CloudBeaver env_file and enable anonymous access ([458177d](https://github.com/stefanko-ch/Nexus-Stack/commit/458177d42ec9d05768706e967356be9e0d537269))
* **stacks:** Fix code-server 502 caused by escaped variable in command ([6950837](https://github.com/stefanko-ch/Nexus-Stack/commit/69508371f87ec83ec8318876d4187cb0082db13b))
* **stacks:** Fix Dagster container naming and config ([5a98a0d](https://github.com/stefanko-ch/Nexus-Stack/commit/5a98a0df6268e27adb11d41112a4025649bb6295))
* **stacks:** Fix Dify nginx healthcheck for 307 redirect ([68f8a99](https://github.com/stefanko-ch/Nexus-Stack/commit/68f8a9994b0177fa1ebc063c6792e048cf8e8daa))
* **stacks:** Fix Jupyter crash due to nounset flag in sourced hook ([f3e3fa3](https://github.com/stefanko-ch/Nexus-Stack/commit/f3e3fa38b34ba35c0d88da16e2633c26fd1a289e))
* **stacks:** Fix Jupyter crash due to nounset flag in sourced hook ([c6f3142](https://github.com/stefanko-ch/Nexus-Stack/commit/c6f3142addf66bafefc33f8277e0ba5c69c500a3))
* **stacks:** Fix MinIO image tag and Filestash admin password ([f9c041a](https://github.com/stefanko-ch/Nexus-Stack/commit/f9c041adb9df134516331fd80505b308f3df3b29))
* **stacks:** Fix mirror creation by piping jq payload via stdin ([d959f08](https://github.com/stefanko-ch/Nexus-Stack/commit/d959f089f1043572794ddf7e68050d65a826bf4b))
* **stacks:** Fork workspace repo after mirror is created, not before ([e8d8fd7](https://github.com/stefanko-ch/Nexus-Stack/commit/e8d8fd70d712e205eb27c0403f812883bfed88ba))
* **stacks:** Fork workspace repo even when mirror already exists ([c3e057c](https://github.com/stefanko-ch/Nexus-Stack/commit/c3e057c2a681af5485ab975a2c8d251a36c438c4))
* **stacks:** Increase Dinky memory to 2.5GB ([baee1d1](https://github.com/stefanko-ch/Nexus-Stack/commit/baee1d12656af0c8de4dbad56fbdaa2bfa27cfbd))
* **stacks:** Inject spark/sc into IPython user namespace ([ca9cb85](https://github.com/stefanko-ch/Nexus-Stack/commit/ca9cb854f64cffeead7e2b74cc29efc7e854a698))
* **stacks:** Integrate Woodpecker CI with Gitea forge ([514fceb](https://github.com/stefanko-ch/Nexus-Stack/commit/514fcebe2b76f062a8b02809c0f0ed8f3cec0e8b))
* **stacks:** Make Debezium internal-only (no subdomain) ([e685831](https://github.com/stefanko-ch/Nexus-Stack/commit/e685831eea7641c5170a15b356ad25743afd9c89))
* **stacks:** Move PySpark kernel config to standalone files ([514f0ea](https://github.com/stefanko-ch/Nexus-Stack/commit/514f0eabe11850d002b647463391db46fabbc806))
* **stacks:** Move Superset admin setup from docker-compose command to deploy.sh ([7f7c045](https://github.com/stefanko-ch/Nexus-Stack/commit/7f7c04580fc70e879c99253f4dc047c186c280ef))
* **stacks:** Pipe jq payload via stdin to fix SSH variable passing ([165a95f](https://github.com/stefanko-ch/Nexus-Stack/commit/165a95f151708b8b58a51be57e9d98b23f66efb8))
* **stacks:** Remove custom healthcheck from Woodpecker server ([6f2227e](https://github.com/stefanko-ch/Nexus-Stack/commit/6f2227eb1f8d684993db9197da90aa286048049d))
* **stacks:** Remove duplicate build directive from Spark worker ([3df169a](https://github.com/stefanko-ch/Nexus-Stack/commit/3df169a6070c4f7de1e101a33661a2e0487851e5))
* **stacks:** Remove https:// prefix from S3 Manager endpoint ([e1c0227](https://github.com/stefanko-ch/Nexus-Stack/commit/e1c0227c850e5ff11d496d14e94a1deba491b044))
* **stacks:** Remove invalid characters from Flink image field ([e46b614](https://github.com/stefanko-ch/Nexus-Stack/commit/e46b6149b3c6b05ca6f1bbfdf774f5d41955b4eb))
* **stacks:** Remove Spark worker volume to fix executor permissions ([942f931](https://github.com/stefanko-ch/Nexus-Stack/commit/942f9312e151811165368b35c8261d90b8929589))
* **stacks:** Rename dify-nginx container to dify for deploy.sh health check ([e90abee](https://github.com/stefanko-ch/Nexus-Stack/commit/e90abee0827fdf898902de887d909f4a2dccf947))
* **stacks:** Rename mirror secrets to avoid reserved GITHUB_ prefix ([b54ed9b](https://github.com/stefanko-ch/Nexus-Stack/commit/b54ed9bb37d928f81d281f266c86d58ec67494eb))
* **stacks:** Rename openmetadata-server container to openmetadata ([7f81ae5](https://github.com/stefanko-ch/Nexus-Stack/commit/7f81ae54da541a5bdc9387c35eea90474f2a0d9b))
* **stacks:** Rename s3manager subdomain and add missing REGION env var ([3e6a92c](https://github.com/stefanko-ch/Nexus-Stack/commit/3e6a92c2e9d264725881f0e459e8aea23d17281b))
* **stacks:** Rename spark-master container to spark for deploy verification ([6f539e8](https://github.com/stefanko-ch/Nexus-Stack/commit/6f539e893815f29ceafdf597c383ec464b27801f))
* **stacks:** Replace curl healthcheck with bash /dev/tcp for Spark ([06840f8](https://github.com/stefanko-ch/Nexus-Stack/commit/06840f83e07846484776d8e4c9c5b96aa2d5af27))
* **stacks:** Restart git services after fork, not before ([11db7de](https://github.com/stefanko-ch/Nexus-Stack/commit/11db7de77129f4ecec04b4b8f247764aa74b19e8))
* **stacks:** Revert code-server to latest (tag :4 doesn't exist) ([ff31fcd](https://github.com/stefanko-ch/Nexus-Stack/commit/ff31fcdb2aea1d21aa70c697a4ad81182d6d6c6f))
* **stacks:** Run Spark Master/Worker in foreground via spark-class ([eca4b59](https://github.com/stefanko-ch/Nexus-Stack/commit/eca4b59da1e47c0b7cc17914fd07ef0403b71bd8))
* **stacks:** Save/restore shell options in sourced Jupyter hook ([1bbeb22](https://github.com/stefanko-ch/Nexus-Stack/commit/1bbeb221631bca1634751387d029cad3033481a0))
* **stacks:** Set Dinky default language to English ([2abe33c](https://github.com/stefanko-ch/Nexus-Stack/commit/2abe33cd3cf0c6a08f03dfe76c03abaa35d82bc7))
* **stacks:** Set PREFECT_UI_API_URL for Cloudflare Tunnel access ([6d9f9ef](https://github.com/stefanko-ch/Nexus-Stack/commit/6d9f9efaebba0152f43927ca6d888b3ee915db25))
* **stacks:** Simplify Redpanda Connect streams mode startup ([a196bac](https://github.com/stefanko-ch/Nexus-Stack/commit/a196bacca7bbe89ff2fd3079ef3e74e893b6ae69))
* **stacks:** Split Woodpecker Gitea URL into internal API + public OAuth ([d19833d](https://github.com/stefanko-ch/Nexus-Stack/commit/d19833d23f28cff10cb643acf0aaf06d6ba4456b))
* **stacks:** Sync Gitea admin and user passwords on spin-up ([23e6bfb](https://github.com/stefanko-ch/Nexus-Stack/commit/23e6bfbc99969b7992ca69cb8541e527df07bf56))
* **stacks:** Sync Gitea DB password on spin-up to handle persistent volume state mismatch ([00152e9](https://github.com/stefanko-ch/Nexus-Stack/commit/00152e9d13264811257d1d54e933844f1764625e))
* **stacks:** Update MinIO image to valid quay.io tag ([3085caf](https://github.com/stefanko-ch/Nexus-Stack/commit/3085caf53851f60ccea28ec2d18514ef8d1f1c28))
* **stacks:** Use before-notebook.d hook for S3A JARs and rebuild on deploy ([e6826db](https://github.com/stefanko-ch/Nexus-Stack/commit/e6826dbf645f07178d221d10fc726a7e0fcef674))
* **stacks:** Use correct kernel path for pyspark-notebook image ([754631b](https://github.com/stefanko-ch/Nexus-Stack/commit/754631b1e3a08aae72bb6a4b1bdae7b9ce92c35a))
* **stacks:** Use correct NC_DB connection string format for NocoDB ([53618fe](https://github.com/stefanko-ch/Nexus-Stack/commit/53618fe390afad1d24729ef50f0cc1c36084b7a3))
* **stacks:** Use correct v3 env var for Woodpecker OAuth redirect ([3db50cc](https://github.com/stefanko-ch/Nexus-Stack/commit/3db50cc611f3a0e4ed4037701c70815977391f50))
* **stacks:** Use default expansion for GITEA_TOKEN to avoid unbound variable error ([a819bcf](https://github.com/stefanko-ch/Nexus-Stack/commit/a819bcf4455320903b239c43f172c025e56d6c9c))
* **stacks:** Use distinct image tag for custom Dinky build ([ad3d086](https://github.com/stefanko-ch/Nexus-Stack/commit/ad3d086eb052fc571c9de0dc4da48cfe1a521516))
* **stacks:** Use distinct image tag for custom Flink build ([d300cbc](https://github.com/stefanko-ch/Nexus-Stack/commit/d300cbc1fc7346369431b32ddbf4aa7f22f6c195))
* **stacks:** Use Docker Library flink image for ARM64 support ([1a3bd1d](https://github.com/stefanko-ch/Nexus-Stack/commit/1a3bd1ded74e1bec961ad75b7ebc614f2af792f4))
* **stacks:** Use entrypoint instead of command for code-server ([fe5186d](https://github.com/stefanko-ch/Nexus-Stack/commit/fe5186d95b8b750e17e10538a62c6bb8360038cd))
* **stacks:** Use jupyterlab package for uv tool install ([490ed12](https://github.com/stefanko-ch/Nexus-Stack/commit/490ed12968acc8a381c74669d15cff2f4197e923))
* **stacks:** Use latest tag for drawio Docker image ([e7c2f2e](https://github.com/stefanko-ch/Nexus-Stack/commit/e7c2f2eb8ed213e8d51940b2b6b17f73c924e34a))
* **stacks:** Use ollama CLI for healthcheck instead of curl ([dfa4d24](https://github.com/stefanko-ch/Nexus-Stack/commit/dfa4d24ae63cc6d6ae5e2975c0305de4662e3ea8))
* **stacks:** Use printf instead of echo for JSON payload piping ([986d502](https://github.com/stefanko-ch/Nexus-Stack/commit/986d5025fe38595c4828782a5445a26673af9473))
* **stacks:** Use public Gitea URL for Woodpecker OAuth and make Gitea core ([1cd7337](https://github.com/stefanko-ch/Nexus-Stack/commit/1cd73376dfafc69ed7244d05138e12fff779359a))
* **stacks:** Use versioned nexus-dagster image tag ([8e4f470](https://github.com/stefanko-ch/Nexus-Stack/commit/8e4f470f216474ca931a83b6b947eccced4641f2))
* **stacks:** Wrap Superset reset-password in || true to prevent startup failure ([022c708](https://github.com/stefanko-ch/Nexus-Stack/commit/022c708e5030879ffc0f837c94f0f22c5438d48a))
* **tofu:** Add force_destroy to Hetzner Object Storage buckets ([21bb02d](https://github.com/stefanko-ch/Nexus-Stack/commit/21bb02db23220df4cce1be467f20fac5104a6e76))
* **tofu:** Exclude public services from Cloudflare Access Application ([06d2495](https://github.com/stefanko-ch/Nexus-Stack/commit/06d24955065eb87e186c0035d0a0297dfceb87b1))
* **tofu:** Fix Hetzner Object Storage bucket ACL error on re-deploy ([9ca1b23](https://github.com/stefanko-ch/Nexus-Stack/commit/9ca1b236bbc322ba9981c0eb59ee37d2820c993b))
* **tofu:** Fix Hetzner Object Storage bucket ACL error on re-deploy ([97df4db](https://github.com/stefanko-ch/Nexus-Stack/commit/97df4dba3a6d3e34b8c9f05bf4dce169c553e44c))
* **tofu:** merge worker cron triggers into single resource ([9ac5059](https://github.com/stefanko-ch/Nexus-Stack/commit/9ac505951e1e37fe4d25e1bdc6e186ecbee74111))
* **tofu:** Pin minio provider to v3.20.0 ([5658e58](https://github.com/stefanko-ch/Nexus-Stack/commit/5658e587973989ea9ba89307b4b435b746db6be5))
* Update post-startup Filestash config to include R2 as primary ([6424675](https://github.com/stefanko-ch/Nexus-Stack/commit/64246750abace19566f1d28ceaf7ae1e4b9ed9e1))
* **windmill:** Auto-configure admin user with generated credentials ([373562b](https://github.com/stefanko-ch/Nexus-Stack/commit/373562b801598110fd39c8751590fd3a412ec22f))
* **windmill:** Create user account for $USER_EMAIL if configured ([748f9c5](https://github.com/stefanko-ch/Nexus-Stack/commit/748f9c5b6280e8ca4b9b276a55fd8bca339a6e38))
* **worker:** address PR review feedback for infra status check ([2d9594f](https://github.com/stefanko-ch/Nexus-Stack/commit/2d9594f90e61c99123eb7f190bdcab6829a38fee))
* **worker:** skip scheduled teardown when infrastructure is not deployed ([4541e7c](https://github.com/stefanko-ch/Nexus-Stack/commit/4541e7cc581a7d43cf8399345546ad79e238be61))


### ♻️ Refactoring

* **control-plane:** Merge Database and Logs into Monitoring page ([dbbba17](https://github.com/stefanko-ch/Nexus-Stack/commit/dbbba177dc3c1e26f8744ca9b24b4f587e75e632))
* **control-plane:** Migrate from static HTML to Astro framework ([ca08738](https://github.com/stefanko-ch/Nexus-Stack/commit/ca0873867296fb95210147eb7aa3ea1b443997bf))
* **control-plane:** Migrate to Astro, add Secrets page and Stack Management ([f7bd8ac](https://github.com/stefanko-ch/Nexus-Stack/commit/f7bd8ac76733a6428c88031f9d7b6aa5fab309d5))
* **control-plane:** Move settings and info to dedicated settings page ([d656f16](https://github.com/stefanko-ch/Nexus-Stack/commit/d656f16ed0cac4a6f94195154be9acf0b576d441))
* **control-plane:** Unify design with shared styles.css ([ea0d78a](https://github.com/stefanko-ch/Nexus-Stack/commit/ea0d78ae913d02b89c48df5697a9ada486c5e237))
* **docs:** Split stacks.md into individual per-stack files ([f639bb3](https://github.com/stefanko-ch/Nexus-Stack/commit/f639bb39bd0922e5294655ed04cd4663dc82d6e1))
* **docs:** Split stacks.md into individual per-stack files ([e14ffe6](https://github.com/stefanko-ch/Nexus-Stack/commit/e14ffe6976f519c048d3c9cf09c98eadac53f737))
* Reorganize Infisical secrets into folders with idempotent push ([891ddc3](https://github.com/stefanko-ch/Nexus-Stack/commit/891ddc38bab920f4631bd5359453b59c41c163f5))
* **stacks:** Derive workspace repo from GH_MIRROR_REPOS automatically ([94ab49b](https://github.com/stefanko-ch/Nexus-Stack/commit/94ab49ba9e2a8f19efe3a57cfa788d1a33907255))
* **stacks:** Simplify WORKSPACE_GIT_REPO to plain repo name ([c363ccd](https://github.com/stefanko-ch/Nexus-Stack/commit/c363ccd18fc1653e2e853c8dfd3128e58b5bfcc5))
* **stacks:** Split 'Databases & Storage' into 'Databases' and 'Storage' ([3d35f9d](https://github.com/stefanko-ch/Nexus-Stack/commit/3d35f9d9ed81e6029707826b63005f17b1d3ab36))


### 📚 Documentation

* Add critical review guideline for Copilot PR comments ([91186a0](https://github.com/stefanko-ch/Nexus-Stack/commit/91186a0b2a9b7209602457873089f95fc29ddec6))
* Add Git Desktop to git-proxy description ([ff00f66](https://github.com/stefanko-ch/Nexus-Stack/commit/ff00f660621b368743a50ba56a3107e9933dd28b))
* Add git log -S check rule for Copilot review comments ([0f63013](https://github.com/stefanko-ch/Nexus-Stack/commit/0f6301380499b56aecb1bdfd79d2ba7bc22ab329))
* Add missing Cloudflare setup steps to setup guide ([3e15af9](https://github.com/stefanko-ch/Nexus-Stack/commit/3e15af9f4b38a737547b21dd794a13464cc3da29))
* Add missing Cloudflare setup steps to setup guide ([2832ba1](https://github.com/stefanko-ch/Nexus-Stack/commit/2832ba11fa4db77f9ca1e7c354f6a48a9be24150))
* Add note about ARM server availability per Hetzner region ([6cd40ef](https://github.com/stefanko-ch/Nexus-Stack/commit/6cd40ef0527c6522d2a8a5fad163ae7ddad1ff12))
* Add one-branch-at-a-time rule to CLAUDE.md ([344f9b6](https://github.com/stefanko-ch/Nexus-Stack/commit/344f9b6322d75fe03f279598ddc93edabb911f65))
* Add stack count to Available Stacks heading ([23de0e6](https://github.com/stefanko-ch/Nexus-Stack/commit/23de0e614a023fa3b9f116f26947bb8c10eef1b2))
* Add website sync documentation ([7d3ec47](https://github.com/stefanko-ch/Nexus-Stack/commit/7d3ec476394bc520c90fb775454ed12840c89d93))
* **control-plane:** Document teardown extension limits and worker health check ([0f16a97](https://github.com/stefanko-ch/Nexus-Stack/commit/0f16a97e7c898e1310f96927d99169288bb540e1))
* Enforce logs-first debugging approach in CLAUDE.md ([adea6b1](https://github.com/stefanko-ch/Nexus-Stack/commit/adea6b1e90b4841afce3ddc4bef05066dcc468b5))
* Replace Mermaid diagrams with hand-crafted SVGs ([f34b9a9](https://github.com/stefanko-ch/Nexus-Stack/commit/f34b9a986970b69fe10d12b3c03a957bdec4a378))
* **stacks:** Add BlueSky real-time streaming tutorial ([9b0ef2f](https://github.com/stefanko-ch/Nexus-Stack/commit/9b0ef2f50e2bc3f7d2d54d927ea48ee6003562c9))
* **stacks:** Add Prometheus monitoring info to RisingWave docs ([bde8337](https://github.com/stefanko-ch/Nexus-Stack/commit/bde833739cc14fba70c71c1654682fb62c29f27c))
* **stacks:** Clarify exact PAT permissions for GitHub mirror ([9b430cf](https://github.com/stefanko-ch/Nexus-Stack/commit/9b430cf3c7b869d94f82225a4877a7e13f459ff1))
* **stacks:** Clarify mirror skip condition wording ([2ae7d66](https://github.com/stefanko-ch/Nexus-Stack/commit/2ae7d66f90132f80baad3a8100e4690183dba7c8))
* **stacks:** Document Dinky locale workaround ([ee2df2f](https://github.com/stefanko-ch/Nexus-Stack/commit/ee2df2f1a320e97ac16258b9db06ea50abf9671e))
* **stacks:** Expand Ollama docs with CPU-only note and model guide ([af64bf3](https://github.com/stefanko-ch/Nexus-Stack/commit/af64bf33fdff85ec73525a8af8107bc63e98f866))
* **stacks:** Mention S3A JARs in Spark custom image note ([bac2c79](https://github.com/stefanko-ch/Nexus-Stack/commit/bac2c7915c3a127af9329dedf86c4e626829b45b))
* **stacks:** Move stacks overview from website repo to single source of truth ([3e04738](https://github.com/stefanko-ch/Nexus-Stack/commit/3e04738c1a7902b6c9404fde236892a6f0651ea4))
* **stacks:** Move stacks overview to single source of truth ([8895c88](https://github.com/stefanko-ch/Nexus-Stack/commit/8895c88b278b68f4e9882c5e3c6b18f6fc68e974))
* **stacks:** Recommend fine-grained PAT for GitHub mirror setup ([53158ef](https://github.com/stefanko-ch/Nexus-Stack/commit/53158ef7f159213ca9b02353bda7624b33c1c4fa))
* Test website sync trigger ([2244e99](https://github.com/stefanko-ch/Nexus-Stack/commit/2244e9914709462d6bb74c8b57505439c6f11317))
* Test website sync trigger ([bece5d2](https://github.com/stefanko-ch/Nexus-Stack/commit/bece5d2145b999cfb55a1302b9e93db0f3361143))


### 🔧 Maintenance

* **ci:** Migrate Cloudflare Pages to Build Image v3 ([ae896a4](https://github.com/stefanko-ch/Nexus-Stack/commit/ae896a48d1c866e6489314bb2052967133e434f5))
* **ci:** Migrate Cloudflare Pages to Build Image v3 ([2b2a395](https://github.com/stefanko-ch/Nexus-Stack/commit/2b2a395121ffe815d395afa0ec8a1c5482c9a2e4)), closes [#252](https://github.com/stefanko-ch/Nexus-Stack/issues/252)
* **ci:** Update GitHub Actions from Node.js 20 to Node.js 24 ([6e60511](https://github.com/stefanko-ch/Nexus-Stack/commit/6e605110cf81a4f8294b9228c1f1aed5c022137d))
* **ci:** Update GitHub Actions to Node.js 24 ([4f8f8c3](https://github.com/stefanko-ch/Nexus-Stack/commit/4f8f8c3545fedc691f65745c75bd6088c742c5e3)), closes [#251](https://github.com/stefanko-ch/Nexus-Stack/issues/251)
* **ci:** Upgrade actions/setup-node from v4 to v5 (Node.js 24) ([03f6c08](https://github.com/stefanko-ch/Nexus-Stack/commit/03f6c0874d0f5df1457099d478927cf556eb325e))
* **control-plane:** Declare Node &gt;=22.12.0 in package.json engines ([31e0dd8](https://github.com/stefanko-ch/Nexus-Stack/commit/31e0dd87b32350bb90bed619086f76b4f99f6a2a))
* **control-plane:** Upgrade Astro 5 to 6 to fix vite CVEs ([aa76d96](https://github.com/stefanko-ch/Nexus-Stack/commit/aa76d9698604133738c829bb522aad5dfd0c4535))
* **control-plane:** Upgrade Astro 5 to 6 to fix vite CVEs ([d208276](https://github.com/stefanko-ch/Nexus-Stack/commit/d2082762cae39345721ffae3e6ad8fc416a036a4))
* **main:** release 0.10.0 ([64b679d](https://github.com/stefanko-ch/Nexus-Stack/commit/64b679dfeeea659ca8086cd052059b777a5c5c1b))
* **main:** release 0.10.0 ([c71785d](https://github.com/stefanko-ch/Nexus-Stack/commit/c71785d089dec5354c9d134c5d6c9cca227f5a5a))
* **main:** release 0.11.0 ([#178](https://github.com/stefanko-ch/Nexus-Stack/issues/178)) ([ca42003](https://github.com/stefanko-ch/Nexus-Stack/commit/ca42003ef00535cdbe6c3432ae4f4025dca453d2))
* **main:** release 0.12.0 ([d5a3a53](https://github.com/stefanko-ch/Nexus-Stack/commit/d5a3a533b46436a3139f8a7a03b4b298ebda66ac))
* **main:** release 0.12.0 ([89b3c95](https://github.com/stefanko-ch/Nexus-Stack/commit/89b3c95a2a6dfb189fb5abd86d60f820efe7341e))
* **main:** release 0.13.0 ([fb4e3bc](https://github.com/stefanko-ch/Nexus-Stack/commit/fb4e3bcc7c27dc0cde5785eac0c700e3af10cee7))
* **main:** release 0.13.0 ([240c50e](https://github.com/stefanko-ch/Nexus-Stack/commit/240c50e6fb7945f8f36f67e342621ccdd1cda651))
* **main:** release 0.14.0 ([144ae7c](https://github.com/stefanko-ch/Nexus-Stack/commit/144ae7c8de0d99edb0978dc081b46b88a676a294))
* **main:** release 0.14.0 ([f81219d](https://github.com/stefanko-ch/Nexus-Stack/commit/f81219da69c7af92bbe2a2996a2f9d9f74b3d51d))
* **main:** release 0.15.0 ([d814bb0](https://github.com/stefanko-ch/Nexus-Stack/commit/d814bb0fddfe985d15a424937540b0fa61cf3537))
* **main:** release 0.15.0 ([1f1225e](https://github.com/stefanko-ch/Nexus-Stack/commit/1f1225e459fb9dd17e9907b4fa60e1c9b89c53cc))
* **main:** release 0.16.0 ([be06bed](https://github.com/stefanko-ch/Nexus-Stack/commit/be06bed45d1e0765f4bca50e5c6fe9fbdb86924a))
* **main:** release 0.16.0 ([188a3d6](https://github.com/stefanko-ch/Nexus-Stack/commit/188a3d61c7c5949d31409573e5be20a66711973a))
* **main:** release 0.17.0 ([6c4ff46](https://github.com/stefanko-ch/Nexus-Stack/commit/6c4ff46430c86acaa08087ff192543153d47b4b4))
* **main:** release 0.17.0 ([1be835c](https://github.com/stefanko-ch/Nexus-Stack/commit/1be835ccfae4012cdb14381019b57a39b692e738))
* **main:** release 0.18.0 ([d8c3111](https://github.com/stefanko-ch/Nexus-Stack/commit/d8c3111b3255c4e4347f4cefd589ce232920f86b))
* **main:** release 0.18.0 ([fb77a02](https://github.com/stefanko-ch/Nexus-Stack/commit/fb77a027cc0d1d65af2969f045c7919f688c7831))
* **main:** release 0.19.0 ([bfd25c0](https://github.com/stefanko-ch/Nexus-Stack/commit/bfd25c0030374344be382548b0fd290bbc323876))
* **main:** release 0.19.0 ([7b22455](https://github.com/stefanko-ch/Nexus-Stack/commit/7b224557d3c2a39cb11eb89acec3ae31d401cded))
* **main:** release 0.19.1 ([d7aab1f](https://github.com/stefanko-ch/Nexus-Stack/commit/d7aab1fd1c813d2d28816a34dc9aacb199a6839b))
* **main:** release 0.19.1 ([bc0f109](https://github.com/stefanko-ch/Nexus-Stack/commit/bc0f1099965123683e5f29185d3bfce91960c45c))
* **main:** release 0.20.0 ([140fe86](https://github.com/stefanko-ch/Nexus-Stack/commit/140fe86c963ca43be7eda5a8b7851a6d3c791916))
* **main:** release 0.20.0 ([076e18f](https://github.com/stefanko-ch/Nexus-Stack/commit/076e18f533564a7f8ac75047bb2f01514fc756b9))
* **main:** release 0.21.0 ([027b590](https://github.com/stefanko-ch/Nexus-Stack/commit/027b590c38b4eba9701d6d2ad6d380d3d687dba9))
* **main:** release 0.21.0 ([82d1537](https://github.com/stefanko-ch/Nexus-Stack/commit/82d15371ca5ea86bf91435232be95392f410e46c))
* **main:** release 0.22.0 ([361e5f3](https://github.com/stefanko-ch/Nexus-Stack/commit/361e5f3cfdef3b0d3ecc4c3deda174ccd7561993))
* **main:** release 0.22.0 ([58c5045](https://github.com/stefanko-ch/Nexus-Stack/commit/58c504500a335093f64a402a61ad92e19d06a985))
* **main:** release 0.23.0 ([fe49be4](https://github.com/stefanko-ch/Nexus-Stack/commit/fe49be433e4dac9749755cc1c462bc5d687723f2))
* **main:** release 0.23.0 ([62a5d21](https://github.com/stefanko-ch/Nexus-Stack/commit/62a5d21ab962e557d6c6762096b6c1d3a840c7e3))
* **main:** release 0.24.0 ([07a342c](https://github.com/stefanko-ch/Nexus-Stack/commit/07a342ccd96df2dc5a35fb794ebc76b749ed2823))
* **main:** release 0.24.0 ([93b4ea8](https://github.com/stefanko-ch/Nexus-Stack/commit/93b4ea8228e41faeba6b0ff3606ab179f0cd7612))
* **main:** release 0.25.0 ([200c8f4](https://github.com/stefanko-ch/Nexus-Stack/commit/200c8f4ebb81758ecacae9eed9fe168a81acc9df))
* **main:** release 0.25.0 ([1a9b844](https://github.com/stefanko-ch/Nexus-Stack/commit/1a9b8446cdf1c0c2b90975e28bdaa64fe434fec5))
* **main:** release 0.26.0 ([e954e99](https://github.com/stefanko-ch/Nexus-Stack/commit/e954e999d54abb29720a6bc0d628c1b8dac7afe3))
* **main:** release 0.26.0 ([a7aab65](https://github.com/stefanko-ch/Nexus-Stack/commit/a7aab65ff464f1ea9a596204339918fdf3c58f75))
* **main:** release 0.27.0 ([8719f36](https://github.com/stefanko-ch/Nexus-Stack/commit/8719f36d4e4def62e1c9c72673d176c6d224cc24))
* **main:** release 0.27.0 ([e01e576](https://github.com/stefanko-ch/Nexus-Stack/commit/e01e57685886a21f1fa25deb37bd16175bec49e4))
* **main:** release 0.27.1 ([a41c465](https://github.com/stefanko-ch/Nexus-Stack/commit/a41c46541759277a76087ff58129cdbb2922c8f9))
* **main:** release 0.27.1 ([a477f12](https://github.com/stefanko-ch/Nexus-Stack/commit/a477f124eae2080275480e8309380e8ecb9fc0f2))
* **main:** release 0.28.0 ([ceaa347](https://github.com/stefanko-ch/Nexus-Stack/commit/ceaa3476d0cbf8d7e5c78108d7f0ee9df81d2867))
* **main:** release 0.28.0 ([949c0c9](https://github.com/stefanko-ch/Nexus-Stack/commit/949c0c93b45acaee561a72edd97ac51a6471a697))
* **main:** release 0.28.1 ([81d9986](https://github.com/stefanko-ch/Nexus-Stack/commit/81d99867bc5668c9cc0578e23d2a1506b2be6a0a))
* **main:** release 0.28.1 ([1af7ce8](https://github.com/stefanko-ch/Nexus-Stack/commit/1af7ce81bda3cb6d7a7e715faeffeb11cfb33064))
* **main:** release 0.29.0 ([93ea9b9](https://github.com/stefanko-ch/Nexus-Stack/commit/93ea9b96181e45b4e5066f5b2d62e732886058c5))
* **main:** release 0.29.0 ([b492260](https://github.com/stefanko-ch/Nexus-Stack/commit/b492260acb567ff9191f9c4653ae4650e47d1a14))
* **main:** release 0.30.0 ([05aacce](https://github.com/stefanko-ch/Nexus-Stack/commit/05aacceaa01a9d868fed54818ef8141bac548686))
* **main:** release 0.30.0 ([e95c033](https://github.com/stefanko-ch/Nexus-Stack/commit/e95c033e46c771a263aa21ea0777b955471ac6a6))
* **main:** release 0.31.0 ([e017f8a](https://github.com/stefanko-ch/Nexus-Stack/commit/e017f8aec4de4cb07af559e2728f0035763b1087))
* **main:** release 0.31.0 ([db4f734](https://github.com/stefanko-ch/Nexus-Stack/commit/db4f7341817e6dcc27044648538433e3abe9f362))
* **main:** release 0.31.1 ([728edb2](https://github.com/stefanko-ch/Nexus-Stack/commit/728edb275069f824bc71bfc17bff0414b96eb32c))
* **main:** release 0.31.1 ([e6b9926](https://github.com/stefanko-ch/Nexus-Stack/commit/e6b992644b9b8a3b3b4e59b703754446e0621ad5))
* **main:** release 0.31.2 ([0bae85f](https://github.com/stefanko-ch/Nexus-Stack/commit/0bae85f169d9b9488ecdf2010c04efefa80972aa))
* **main:** release 0.31.2 ([7b052ad](https://github.com/stefanko-ch/Nexus-Stack/commit/7b052ad1428ed73fa7da17bebbc3465745a8160a))
* **main:** release 0.32.0 ([e8c0771](https://github.com/stefanko-ch/Nexus-Stack/commit/e8c077129cab801e8758b394cbaaf37c545d2479))
* **main:** release 0.32.0 ([f3b2bfb](https://github.com/stefanko-ch/Nexus-Stack/commit/f3b2bfb5dcf4009a04babd08f861d8c32dab8d14))
* **main:** release 0.33.0 ([3a2543a](https://github.com/stefanko-ch/Nexus-Stack/commit/3a2543a8da48335a3a809fd88a20c9eae597a4f4))
* **main:** release 0.33.0 ([a7c77ca](https://github.com/stefanko-ch/Nexus-Stack/commit/a7c77ca869e04937ee46cfb3e625139ade84a3d8))
* **main:** release 0.34.0 ([04bc2bf](https://github.com/stefanko-ch/Nexus-Stack/commit/04bc2bfe133d7e26a17c2d86f5913ad82185cffb))
* **main:** release 0.34.0 ([b8cc0c4](https://github.com/stefanko-ch/Nexus-Stack/commit/b8cc0c46de965511530af7868e571159d38d6357))
* **main:** release 0.35.0 ([5067680](https://github.com/stefanko-ch/Nexus-Stack/commit/5067680143c96817b1afe2e8a0e7df24804a790b))
* **main:** release 0.35.0 ([3f9071d](https://github.com/stefanko-ch/Nexus-Stack/commit/3f9071dc072f428b11133f2a4285f95d4cdded6c))
* **main:** release 0.36.0 ([f75456b](https://github.com/stefanko-ch/Nexus-Stack/commit/f75456bdcc106fc645f413dc69b675cc1b6906a1))
* **main:** release 0.36.0 ([c08bc39](https://github.com/stefanko-ch/Nexus-Stack/commit/c08bc39a7841b6f555ad8b869499c2785cc33635))
* **main:** release 0.37.0 ([56b1282](https://github.com/stefanko-ch/Nexus-Stack/commit/56b12827d55ae89b5070e2a379751bd7c783e5a3))
* **main:** release 0.37.0 ([e5301cc](https://github.com/stefanko-ch/Nexus-Stack/commit/e5301cccdc1c5c5cfed0f6fd358f8788f539cf91))
* **main:** release 0.38.0 ([1576f6a](https://github.com/stefanko-ch/Nexus-Stack/commit/1576f6a016aa842dc6184cef26dde1da34dd8a36))
* **main:** release 0.38.0 ([1f26e35](https://github.com/stefanko-ch/Nexus-Stack/commit/1f26e359c13227473982b63abc032d7f29301774))
* **main:** release 0.39.0 ([1881000](https://github.com/stefanko-ch/Nexus-Stack/commit/1881000b9defa58102c92b63cb3508c3df0465ac))
* **main:** release 0.39.0 ([599d20b](https://github.com/stefanko-ch/Nexus-Stack/commit/599d20b5278cd3d42397d4dfa34f02d5d5860b19))
* **main:** release 0.40.0 ([111f71b](https://github.com/stefanko-ch/Nexus-Stack/commit/111f71bc7dd21f4b1a1bc2b308fc32458b1ce285))
* **main:** release 0.40.0 ([52bde24](https://github.com/stefanko-ch/Nexus-Stack/commit/52bde242ad01e3ce1d6c0a096ab1ee9297dbc71c))
* **main:** release 0.41.0 ([684a6ff](https://github.com/stefanko-ch/Nexus-Stack/commit/684a6ff1c804f26605ccb5eea03c1c716fe7471b))
* **main:** release 0.41.0 ([7e58d35](https://github.com/stefanko-ch/Nexus-Stack/commit/7e58d35470291961e8beaa0e09680bebd2f8046d))
* **main:** release 0.42.0 ([31d72e1](https://github.com/stefanko-ch/Nexus-Stack/commit/31d72e16241e76fd729d57c828c60a0b36bfba0c))
* **main:** release 0.42.0 ([ac794eb](https://github.com/stefanko-ch/Nexus-Stack/commit/ac794eb89323d46414499a38e7384d8f01b1746d))
* **main:** release 0.43.0 ([91f22d9](https://github.com/stefanko-ch/Nexus-Stack/commit/91f22d90b7759837dd94bf92fd38d75cdcfc6fa3))
* **main:** release 0.43.0 ([1225a6e](https://github.com/stefanko-ch/Nexus-Stack/commit/1225a6eb519e0b193a8169f4b1ad44cf8de66181))
* **main:** release 0.44.0 ([d9e4c5d](https://github.com/stefanko-ch/Nexus-Stack/commit/d9e4c5db159e221edf36933c129ab68eae1721ad))
* **main:** release 0.44.0 ([f0ae7e0](https://github.com/stefanko-ch/Nexus-Stack/commit/f0ae7e0180e822e9bbc8692252dd88f5b09d4af3))
* **main:** release 0.45.0 ([d2ad75b](https://github.com/stefanko-ch/Nexus-Stack/commit/d2ad75b21e7a7150afaf0d4fdd5e31e6c8d5b1dc))
* **main:** release 0.45.0 ([cc63207](https://github.com/stefanko-ch/Nexus-Stack/commit/cc63207dc9d728b4977dea0f18e79e85947d18e2))
* **main:** release 0.45.1 ([7e3db13](https://github.com/stefanko-ch/Nexus-Stack/commit/7e3db1323a80faa10c25facccf62e0504be13e84))
* **main:** release 0.45.1 ([cd5c128](https://github.com/stefanko-ch/Nexus-Stack/commit/cd5c1283be450242eefbbaf41530b0ada9f55338))
* **main:** release 0.45.2 ([34e68db](https://github.com/stefanko-ch/Nexus-Stack/commit/34e68dbad3e00a9b1d7c5519340a953bdeea7ed1))
* **main:** release 0.45.2 ([ea1cc7d](https://github.com/stefanko-ch/Nexus-Stack/commit/ea1cc7d370fda58b79a75f10e0437df2d507ffbd))
* Remove Co-Authored-By trailers from commit convention ([f466899](https://github.com/stefanko-ch/Nexus-Stack/commit/f46689924609e63b9c8f00718cec236191d0548c))
* Remove outdated make command references ([6f07a46](https://github.com/stefanko-ch/Nexus-Stack/commit/6f07a4681b3224ffc00d9252d27ca9163b5fd5f5))

## [0.45.2](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.45.1...v0.45.2) (2026-04-12)


### 🐛 Bug Fixes

* **ci:** Add --region to all Hetzner S3 API calls ([fc66b3e](https://github.com/stefanko-ch/Nexus-Stack/commit/fc66b3e7b683e56b3084f58df93c35673bc151e6))
* **ci:** Add pgducklake bucket to destroy & setup workflows ([31dc739](https://github.com/stefanko-ch/Nexus-Stack/commit/31dc73969c562cabc889d78148db0aa375230068))
* **ci:** Make Hetzner Object Storage non-blocking in setup workflow ([2785b3a](https://github.com/stefanko-ch/Nexus-Stack/commit/2785b3a14c10af74b64b3bef771d2e34b7705686))
* **ci:** Upgrade setup-node v5, fix Hetzner Object Storage resilience ([9970c92](https://github.com/stefanko-ch/Nexus-Stack/commit/9970c92fcb472ed8ab182f9ea47c72b9e1cbf1c3))


### 🔧 Maintenance

* **ci:** Upgrade actions/setup-node from v4 to v5 (Node.js 24) ([03f6c08](https://github.com/stefanko-ch/Nexus-Stack/commit/03f6c0874d0f5df1457099d478927cf556eb325e))

## [0.45.1](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.45.0...v0.45.1) (2026-04-11)


### 🐛 Bug Fixes

* **ci:** Reword fork safety comment to reflect actual gate ([eb32494](https://github.com/stefanko-ch/Nexus-Stack/commit/eb3249445d24f36eb70c81f3ea9b717b3dd7e2a0))
* **ci:** Switch docs sync from repository_dispatch to Cloudflare Deploy Hook ([fe35c0e](https://github.com/stefanko-ch/Nexus-Stack/commit/fe35c0e3e7ff6afd004a697382874a47d471e578))
* **ci:** Switch docs sync to Cloudflare Deploy Hook ([a88c2ff](https://github.com/stefanko-ch/Nexus-Stack/commit/a88c2ff6eac8c87fbd1bdac5af1e4c978dd8546d))
* **docs:** Add pg-ducklake to overview, fix Swiss capitalization ([3c4178a](https://github.com/stefanko-ch/Nexus-Stack/commit/3c4178ab9d59ca341f55eb511d6491eac3fa16d3))
* **docs:** Address PR [#406](https://github.com/stefanko-ch/Nexus-Stack/issues/406) review feedback ([56801a1](https://github.com/stefanko-ch/Nexus-Stack/commit/56801a12cdd9b3c3fb81c8546cb19eb97541f540))
* **docs:** Address PR [#406](https://github.com/stefanko-ch/Nexus-Stack/issues/406) review feedback - fail on missing hook, fix docs ([fe188e9](https://github.com/stefanko-ch/Nexus-Stack/commit/fe188e9673211593896be187cbb93b8ac2432be9))


### 📚 Documentation

* **stacks:** Move stacks overview from website repo to single source of truth ([3e04738](https://github.com/stefanko-ch/Nexus-Stack/commit/3e04738c1a7902b6c9404fde236892a6f0651ea4))
* **stacks:** Move stacks overview to single source of truth ([8895c88](https://github.com/stefanko-ch/Nexus-Stack/commit/8895c88b278b68f4e9882c5e3c6b18f6fc68e974))
* Test website sync trigger ([2244e99](https://github.com/stefanko-ch/Nexus-Stack/commit/2244e9914709462d6bb74c8b57505439c6f11317))
* Test website sync trigger ([bece5d2](https://github.com/stefanko-ch/Nexus-Stack/commit/bece5d2145b999cfb55a1302b9e93db0f3361143))

## [0.45.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.44.0...v0.45.0) (2026-04-11)


### 🚀 Features

* **docs:** Add website sync workflow and frontmatter for nexus-stack.ch ([b235cbf](https://github.com/stefanko-ch/Nexus-Stack/commit/b235cbf54efc856aa8b1b040e0db32949781c174))
* **docs:** Add website sync workflow and frontmatter to all docs ([56a7e8a](https://github.com/stefanko-ch/Nexus-Stack/commit/56a7e8a22094662abd9137e951306384a06674fc)), closes [#399](https://github.com/stefanko-ch/Nexus-Stack/issues/399)


### 🐛 Bug Fixes

* **ci:** Address PR [#404](https://github.com/stefanko-ch/Nexus-Stack/issues/404) review feedback ([06e6043](https://github.com/stefanko-ch/Nexus-Stack/commit/06e60438aed404aa6c2f1d8b84edd9d8a3ee1d21))
* **ci:** Address PR [#405](https://github.com/stefanko-ch/Nexus-Stack/issues/405) review feedback - add permissions block and sync guard ([f8d76f0](https://github.com/stefanko-ch/Nexus-Stack/commit/f8d76f0e5cac3342d3b96921a32f694e73fb9f95))
* **ci:** Use env var for secrets check in step conditions (actionlint) ([5ab83b5](https://github.com/stefanko-ch/Nexus-Stack/commit/5ab83b5a5cfbf824558d97d3ef053f3e1aaae1d0))
* **control-plane:** Add D1 logging to 5 unlogged API endpoints ([a21d8db](https://github.com/stefanko-ch/Nexus-Stack/commit/a21d8db6fd8d26aca163d01cd15c4af67527071b))
* **control-plane:** Address PR [#402](https://github.com/stefanko-ch/Nexus-Stack/issues/402) review feedback ([c1fc22d](https://github.com/stefanko-ch/Nexus-Stack/commit/c1fc22d122d09a7ff121fc7a47d77a5124bd95fd))
* **control-plane:** Use arrayBuffer for byte-accurate body size check ([7416e4a](https://github.com/stefanko-ch/Nexus-Stack/commit/7416e4a54c51f94189126713c39ebb0608cb2dd9))
* **docs:** Address PR [#405](https://github.com/stefanko-ch/Nexus-Stack/issues/405) review feedback - sync guard docs and stack count ([a936c91](https://github.com/stefanko-ch/Nexus-Stack/commit/a936c91531b2ef592b6d59e0f23fb1401c4f0f5f))
* **docs:** Address PR [#405](https://github.com/stefanko-ch/Nexus-Stack/issues/405) review feedback - token guard and security text ([3e6a78c](https://github.com/stefanko-ch/Nexus-Stack/commit/3e6a78c4b25c2ab7c08a171935e2931fa93d054d))
* **docs:** Move bluesky-flink-tutorial from stacks/ to tutorials/ ([d3276c3](https://github.com/stefanko-ch/Nexus-Stack/commit/d3276c3bb397ee9af4566dcad98e5ca2618ecafc))
* **docs:** Redesign architecture SVG with cleaner layout ([854b1d3](https://github.com/stefanko-ch/Nexus-Stack/commit/854b1d3c0c69b55b1017b54716a2be60d7c2e85f))
* **scripts:** Restore LOG_FILE variable used by debug logging ([a3ca51f](https://github.com/stefanko-ch/Nexus-Stack/commit/a3ca51f8bede2b33f708aaf4e6dda3aad7475f97))
* Stability overhaul across infrastructure, workflows, and Docker stacks ([12f7847](https://github.com/stefanko-ch/Nexus-Stack/commit/12f78474282a3db6014d571b8a1c0e0384da7a6f))
* Stability overhaul across infrastructure, workflows, and Docker stacks ([6b359e7](https://github.com/stefanko-ch/Nexus-Stack/commit/6b359e7fcfa051832e5ab7b083fac1fc1094f3d4))


### 📚 Documentation

* Add website sync documentation ([7d3ec47](https://github.com/stefanko-ch/Nexus-Stack/commit/7d3ec476394bc520c90fb775454ed12840c89d93))
* Replace Mermaid diagrams with hand-crafted SVGs ([f34b9a9](https://github.com/stefanko-ch/Nexus-Stack/commit/f34b9a986970b69fe10d12b3c03a957bdec4a378))


### 🔧 Maintenance

* **ci:** Migrate Cloudflare Pages to Build Image v3 ([ae896a4](https://github.com/stefanko-ch/Nexus-Stack/commit/ae896a48d1c866e6489314bb2052967133e434f5))
* **ci:** Migrate Cloudflare Pages to Build Image v3 ([2b2a395](https://github.com/stefanko-ch/Nexus-Stack/commit/2b2a395121ffe815d395afa0ec8a1c5482c9a2e4)), closes [#252](https://github.com/stefanko-ch/Nexus-Stack/issues/252)

## [0.44.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.43.0...v0.44.0) (2026-04-09)


### 🚀 Features

* **control-plane:** Add limits and audit logging to teardown extensions ([84173f8](https://github.com/stefanko-ch/Nexus-Stack/commit/84173f83d739e222c4ac9c0a32ae8b3ca7e78bd5))
* **control-plane:** Add limits and audit logging to teardown extensions ([fa72e91](https://github.com/stefanko-ch/Nexus-Stack/commit/fa72e916a5ca9945acd51856e574c9581128dd82)), closes [#340](https://github.com/stefanko-ch/Nexus-Stack/issues/340)
* **control-plane:** Add post-deploy diagnostic health check for worker ([61c5254](https://github.com/stefanko-ch/Nexus-Stack/commit/61c52546f7faaa47acb9f867bf6821bc91a13d6b))


### 🐛 Bug Fixes

* **ci:** Pin Node.js 22 in setup-control-plane and spin-up workflows ([438d71a](https://github.com/stefanko-ch/Nexus-Stack/commit/438d71a1f050beca05c034119e8c2bbcaf555bd1))
* **control-plane:** Address PR [#341](https://github.com/stefanko-ch/Nexus-Stack/issues/341) review feedback ([8459409](https://github.com/stefanko-ch/Nexus-Stack/commit/84594099101c733bff9b16601fd0b1a7cdd7894c))
* **control-plane:** Enable workers.dev subdomain via API instead of TF resource ([4122176](https://github.com/stefanko-ch/Nexus-Stack/commit/4122176ba3c8b5773b8cb73a3033c8e506f24b6b))


### 📚 Documentation

* **control-plane:** Document teardown extension limits and worker health check ([0f16a97](https://github.com/stefanko-ch/Nexus-Stack/commit/0f16a97e7c898e1310f96927d99169288bb540e1))


### 🔧 Maintenance

* **control-plane:** Declare Node &gt;=22.12.0 in package.json engines ([31e0dd8](https://github.com/stefanko-ch/Nexus-Stack/commit/31e0dd87b32350bb90bed619086f76b4f99f6a2a))
* **control-plane:** Upgrade Astro 5 to 6 to fix vite CVEs ([aa76d96](https://github.com/stefanko-ch/Nexus-Stack/commit/aa76d9698604133738c829bb522aad5dfd0c4535))
* **control-plane:** Upgrade Astro 5 to 6 to fix vite CVEs ([d208276](https://github.com/stefanko-ch/Nexus-Stack/commit/d2082762cae39345721ffae3e6ad8fc416a036a4))

## [0.43.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.42.0...v0.43.0) (2026-04-09)


### 🚀 Features

* **stacks:** Add pg_ducklake - PostgreSQL with DuckLake extension ([7cf0ade](https://github.com/stefanko-ch/Nexus-Stack/commit/7cf0aded8f8848ef0e2a0a569caa97135d847114))
* **stacks:** Add pg_ducklake - PostgreSQL with DuckLake extension ([9699124](https://github.com/stefanko-ch/Nexus-Stack/commit/9699124a781b2a79f28d9eb423c8ccd9f29c340a)), closes [#331](https://github.com/stefanko-ch/Nexus-Stack/issues/331)


### 🐛 Bug Fixes

* **scripts:** Require full S3 var set before generating pg_ducklake S3 secret ([c14c09e](https://github.com/stefanko-ch/Nexus-Stack/commit/c14c09eab0a99df5c50b08dc6508cef87ce82a0f))

## [0.42.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.41.0...v0.42.0) (2026-04-02)


### 🚀 Features

* **control-plane:** Fetch secrets live from Infisical API instead of static JSON ([d8d81c4](https://github.com/stefanko-ch/Nexus-Stack/commit/d8d81c443a96e39d95a8c0c599615af096b0d9d7))
* **stacks:** Add Apache Superset data exploration platform ([7f38ed2](https://github.com/stefanko-ch/Nexus-Stack/commit/7f38ed242d53a2c6f432c3c65558bf192d485fbf))
* **stacks:** Add Apache Superset stack, fetch Control Plane secrets from Infisical ([7dd6c45](https://github.com/stefanko-ch/Nexus-Stack/commit/7dd6c45836dd617bc296fc988b1830665aca41b1))


### 🐛 Bug Fixes

* **ci:** Read both Infisical token and project ID from server via SSH before port closes ([9c98665](https://github.com/stefanko-ch/Nexus-Stack/commit/9c986656d4d3e284bea2e49be465cec7d7f9516c))
* **ci:** Read Infisical project ID before SSH port closes, use job-level token var ([1edd07c](https://github.com/stefanko-ch/Nexus-Stack/commit/1edd07c6d59b0bc465f9699bcdfdb3633399e40a))
* **control-plane:** Address PR review - restore CF-Access auth check, use env for Infisical env, surface warnings ([513954b](https://github.com/stefanko-ch/Nexus-Stack/commit/513954bd697213ad845cb42d989100dea6729924))
* **control-plane:** Fix Secrets page by adding CF Access Service Token for Infisical API ([3318059](https://github.com/stefanko-ch/Nexus-Stack/commit/331805984c774b36618807e73504dcdc327912b2))
* **control-plane:** Pin wrangler@4 for pages secret put, rename root secrets group to avoid collision ([4b40565](https://github.com/stefanko-ch/Nexus-Stack/commit/4b40565ecfb3cc85cfbc431099d47a3be80bbc49))
* **control-plane:** Remove CF-Access header check that breaks Pages Functions ([af94a06](https://github.com/stefanko-ch/Nexus-Stack/commit/af94a064790aecf2d6a4c232a6ebf46ec8cf98f3))
* **control-plane:** Remove strict CF-Access header check on secrets API, fix search dropdown styles ([c52ba61](https://github.com/stefanko-ch/Nexus-Stack/commit/c52ba610e9046ecc74fb99116a446a910c572129))
* **stacks:** Add password reset on Superset startup to fix Invalid login ([33f1713](https://github.com/stefanko-ch/Nexus-Stack/commit/33f1713931e786575b73d60a28b0e6c76026b105))
* **stacks:** Address Superset PR review - isolate create-admin failure, push all secrets to Infisical ([82b8ff0](https://github.com/stefanko-ch/Nexus-Stack/commit/82b8ff0531a1e18b9ae18ab65cd001888f398efc))
* **stacks:** Move Superset admin setup from docker-compose command to deploy.sh ([7f7c045](https://github.com/stefanko-ch/Nexus-Stack/commit/7f7c04580fc70e879c99253f4dc047c186c280ef))
* **stacks:** Wrap Superset reset-password in || true to prevent startup failure ([022c708](https://github.com/stefanko-ch/Nexus-Stack/commit/022c708e5030879ffc0f837c94f0f22c5438d48a))


### 📚 Documentation

* Add git log -S check rule for Copilot review comments ([0f63013](https://github.com/stefanko-ch/Nexus-Stack/commit/0f6301380499b56aecb1bdfd79d2ba7bc22ab329))

## [0.41.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.40.0...v0.41.0) (2026-04-02)


### 🚀 Features

* **control-plane:** Add Secrets page with grouped, masked credentials ([43a6013](https://github.com/stefanko-ch/Nexus-Stack/commit/43a6013b433b52d0c815bd046d53c353f3a1d298))
* **control-plane:** Redesign Control Panel with category-based navigation ([89998c5](https://github.com/stefanko-ch/Nexus-Stack/commit/89998c5c7be9483c4b722903dd0b080d99454157))
* **control-plane:** Remove info page, add Open links to service cards ([9ced111](https://github.com/stefanko-ch/Nexus-Stack/commit/9ced111ed080aa0140755a04a2c1f01f9ea98805))


### 🐛 Bug Fixes

* **ci:** Update spin-up workflow for Astro build (control-plane/pages removed) ([b088ec0](https://github.com/stefanko-ch/Nexus-Stack/commit/b088ec0656462657c7e99150d89ab86ff23f8f5d))
* **control-plane:** Address PR review comments for XSS, auth, and cleanup ([efb3457](https://github.com/stefanko-ch/Nexus-Stack/commit/efb34574b873936152ac1624bfe68f16e046d901))
* **control-plane:** Destructure request from context in services API ([81dc49e](https://github.com/stefanko-ch/Nexus-Stack/commit/81dc49eb79cde53661723232021417d80cf4e23e))
* **control-plane:** Fix settings.html API response parsing ([92e75d1](https://github.com/stefanko-ch/Nexus-Stack/commit/92e75d1bddd5321d0ee1b9e48472a23f54574d09))
* **control-plane:** Fix stack chips styling with :global for dynamic elements ([77d6065](https://github.com/stefanko-ch/Nexus-Stack/commit/77d6065ad2d194e768e330f2d0c130ce0df67b24))
* **control-plane:** Guard removed DOM elements and remove stale init calls ([a1edd09](https://github.com/stefanko-ch/Nexus-Stack/commit/a1edd09f4ceda02df5f4098af06b59ae32125adc))
* **control-plane:** Redesign active stacks as clickable chip buttons ([780e5ae](https://github.com/stefanko-ch/Nexus-Stack/commit/780e5aeac4a8f9a3f2d29428ff1dca9ad0a7bcd1))
* **control-plane:** Remove all dead JS functions and event listeners ([6eef679](https://github.com/stefanko-ch/Nexus-Stack/commit/6eef679a1039ad554d6f06b0ae13e126378229ac))
* **control-plane:** Stack chips as vertical list in boxes ([2d09783](https://github.com/stefanko-ch/Nexus-Stack/commit/2d0978397c6a144f914f3e15c1501799dbf1ab84))


### ♻️ Refactoring

* **control-plane:** Merge Database and Logs into Monitoring page ([dbbba17](https://github.com/stefanko-ch/Nexus-Stack/commit/dbbba177dc3c1e26f8744ca9b24b4f587e75e632))
* **control-plane:** Migrate from static HTML to Astro framework ([ca08738](https://github.com/stefanko-ch/Nexus-Stack/commit/ca0873867296fb95210147eb7aa3ea1b443997bf))
* **control-plane:** Migrate to Astro, add Secrets page and Stack Management ([f7bd8ac](https://github.com/stefanko-ch/Nexus-Stack/commit/f7bd8ac76733a6428c88031f9d7b6aa5fab309d5))
* **control-plane:** Move settings and info to dedicated settings page ([d656f16](https://github.com/stefanko-ch/Nexus-Stack/commit/d656f16ed0cac4a6f94195154be9acf0b576d441))
* **control-plane:** Unify design with shared styles.css ([ea0d78a](https://github.com/stefanko-ch/Nexus-Stack/commit/ea0d78ae913d02b89c48df5697a9ada486c5e237))
* **stacks:** Split 'Databases & Storage' into 'Databases' and 'Storage' ([3d35f9d](https://github.com/stefanko-ch/Nexus-Stack/commit/3d35f9d9ed81e6029707826b63005f17b1d3ab36))

## [0.40.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.39.0...v0.40.0) (2026-04-02)


### 🚀 Features

* **stacks:** Add Vector and Telegraf observability agents ([3dd73b1](https://github.com/stefanko-ch/Nexus-Stack/commit/3dd73b117471bde64361c8be48ac8f353674e7c7))
* **stacks:** Add Vector and Telegraf observability agents ([d09f92e](https://github.com/stefanko-ch/Nexus-Stack/commit/d09f92ece9a8d9e01824e434a086b437a29add26)), closes [#316](https://github.com/stefanko-ch/Nexus-Stack/issues/316) [#317](https://github.com/stefanko-ch/Nexus-Stack/issues/317)


### 🐛 Bug Fixes

* **stacks:** Address Vector/Telegraf PR review comments ([7e217e1](https://github.com/stefanko-ch/Nexus-Stack/commit/7e217e139670570dc1e642dfd8a74065b6ee1f96))

## [0.39.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.38.0...v0.39.0) (2026-04-01)


### 🚀 Features

* **stacks:** Add Sling data integration CLI tool ([7e005ec](https://github.com/stefanko-ch/Nexus-Stack/commit/7e005ec7b3c44b5784fdd34ea60045600a55d960))
* **stacks:** Add Sling data integration CLI tool ([29d10b0](https://github.com/stefanko-ch/Nexus-Stack/commit/29d10b0e46219ba7d4c03eb58be3b4e9ead0a833)), closes [#311](https://github.com/stefanko-ch/Nexus-Stack/issues/311)


### 🐛 Bug Fixes

* **stacks:** Address Sling PR review comments ([6c4df8c](https://github.com/stefanko-ch/Nexus-Stack/commit/6c4df8c83e9185e630968342506360b808c3573a))

## [0.38.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.37.0...v0.38.0) (2026-04-01)


### 🚀 Features

* **stacks:** Add Debezium CDC platform ([b552997](https://github.com/stefanko-ch/Nexus-Stack/commit/b552997e3d6ed6547579be7c03112cbaf2bcaf9a))
* **stacks:** Add Debezium CDC platform ([4aaf153](https://github.com/stefanko-ch/Nexus-Stack/commit/4aaf15383e462211b93523690dd5a28db4da428d)), closes [#235](https://github.com/stefanko-ch/Nexus-Stack/issues/235)


### 🐛 Bug Fixes

* **docs:** Align Debezium docs with internal_only access model ([54a928e](https://github.com/stefanko-ch/Nexus-Stack/commit/54a928e4b73e6484f60615600932e3d172b7d411))
* **stacks:** Address Debezium PR review comments ([efdb14d](https://github.com/stefanko-ch/Nexus-Stack/commit/efdb14df13f49dc2a2f1db960e9d78a5a6071e09))
* **stacks:** Make Debezium internal-only (no subdomain) ([e685831](https://github.com/stefanko-ch/Nexus-Stack/commit/e685831eea7641c5170a15b356ad25743afd9c89))

## [0.37.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.36.0...v0.37.0) (2026-04-01)


### 🚀 Features

* **stacks:** Add Dagster data orchestration platform ([85db108](https://github.com/stefanko-ch/Nexus-Stack/commit/85db108cd037dc380bccf3e20490a05690ef9512))
* **stacks:** Add Dagster data orchestration platform ([8ae9a3c](https://github.com/stefanko-ch/Nexus-Stack/commit/8ae9a3c01976709c6c3d3dfb536ce4bf55248959)), closes [#161](https://github.com/stefanko-ch/Nexus-Stack/issues/161)


### 🐛 Bug Fixes

* **stacks:** Fix Dagster container naming and config ([5a98a0d](https://github.com/stefanko-ch/Nexus-Stack/commit/5a98a0df6268e27adb11d41112a4025649bb6295))
* **stacks:** Use versioned nexus-dagster image tag ([8e4f470](https://github.com/stefanko-ch/Nexus-Stack/commit/8e4f470f216474ca931a83b6b947eccced4641f2))

## [0.36.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.35.0...v0.36.0) (2026-04-01)


### 🚀 Features

* **stacks:** Add Budibase low-code platform ([dc60df7](https://github.com/stefanko-ch/Nexus-Stack/commit/dc60df7f68b35a36a3baedb9b290f474b6cffd30))
* **stacks:** Add Budibase low-code platform ([c807f99](https://github.com/stefanko-ch/Nexus-Stack/commit/c807f994b0179b45057f9d5dff905bc7427a3306)), closes [#246](https://github.com/stefanko-ch/Nexus-Stack/issues/246)

## [0.35.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.34.0...v0.35.0) (2026-04-01)


### 🚀 Features

* **stacks:** Add Kafdrop Kafka/Redpanda web UI ([4ad8a00](https://github.com/stefanko-ch/Nexus-Stack/commit/4ad8a0001f04085e07cf6338a8691c1b790f18ad))
* **stacks:** Add Kafdrop Kafka/Redpanda web UI ([951f8ae](https://github.com/stefanko-ch/Nexus-Stack/commit/951f8ae2ff255a6aad5a04501b0b2cd7c7b45544)), closes [#40](https://github.com/stefanko-ch/Nexus-Stack/issues/40)

## [0.34.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.33.0...v0.34.0) (2026-04-01)


### 🚀 Features

* **stacks:** Add AKHQ Kafka/Redpanda management GUI ([c4fad8b](https://github.com/stefanko-ch/Nexus-Stack/commit/c4fad8ba0712f7c4a7a1d874e4cafb394ef9c8c6))
* **stacks:** Add AKHQ Kafka/Redpanda management GUI ([f28c9b7](https://github.com/stefanko-ch/Nexus-Stack/commit/f28c9b75520b731e81b811cbcd4ffdeaac6fdb2c)), closes [#41](https://github.com/stefanko-ch/Nexus-Stack/issues/41)


### 🐛 Bug Fixes

* **docs:** Align AKHQ version strategy and description ([f8d78dd](https://github.com/stefanko-ch/Nexus-Stack/commit/f8d78dd72510fa0441e5598fbc29ad0daae8f46d))

## [0.33.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.32.0...v0.33.0) (2026-03-31)


### 🚀 Features

* **stacks:** Add Dinky Flink SQL IDE ([3e1f213](https://github.com/stefanko-ch/Nexus-Stack/commit/3e1f213e6ce630ce79996a122b8d6c8ec76f6099))
* **stacks:** Add Dinky Flink SQL IDE ([9e65bb1](https://github.com/stefanko-ch/Nexus-Stack/commit/9e65bb1e3ba200f5764bfa94edfab3fd29c4a24e)), closes [#294](https://github.com/stefanko-ch/Nexus-Stack/issues/294)
* **stacks:** Bake Kafka SQL connector into Dinky image ([f945f8f](https://github.com/stefanko-ch/Nexus-Stack/commit/f945f8f529a92bde6b70c1502f72873a7120457f))
* **stacks:** Bake Kafka SQL connector into Flink image ([e305ac3](https://github.com/stefanko-ch/Nexus-Stack/commit/e305ac38db4251ad7ecc587982792e4b9469e105))
* **stacks:** Switch Redpanda Connect to streams mode ([47506fb](https://github.com/stefanko-ch/Nexus-Stack/commit/47506fbeff02fda465591901722e65610c69fa1c))


### 🐛 Bug Fixes

* **docs:** Correct footnote and Dinky resource limits ([e4cf353](https://github.com/stefanko-ch/Nexus-Stack/commit/e4cf35311e612cfadfea02833ece25a9f21ef587))
* **stacks:** Add MySQL JDBC driver to Dinky for persistent catalog ([399b53c](https://github.com/stefanko-ch/Nexus-Stack/commit/399b53c81b96313d586a14c55a24dc768b3dd93a))
* **stacks:** Address PR review comments for Dinky ([4664c66](https://github.com/stefanko-ch/Nexus-Stack/commit/4664c66e9107ee6743f72094e66edf1d1f16df3f))
* **stacks:** Increase Dinky memory to 2.5GB ([baee1d1](https://github.com/stefanko-ch/Nexus-Stack/commit/baee1d12656af0c8de4dbad56fbdaa2bfa27cfbd))
* **stacks:** Remove invalid characters from Flink image field ([e46b614](https://github.com/stefanko-ch/Nexus-Stack/commit/e46b6149b3c6b05ca6f1bbfdf774f5d41955b4eb))
* **stacks:** Set Dinky default language to English ([2abe33c](https://github.com/stefanko-ch/Nexus-Stack/commit/2abe33cd3cf0c6a08f03dfe76c03abaa35d82bc7))
* **stacks:** Simplify Redpanda Connect streams mode startup ([a196bac](https://github.com/stefanko-ch/Nexus-Stack/commit/a196bacca7bbe89ff2fd3079ef3e74e893b6ae69))
* **stacks:** Use distinct image tag for custom Dinky build ([ad3d086](https://github.com/stefanko-ch/Nexus-Stack/commit/ad3d086eb052fc571c9de0dc4da48cfe1a521516))
* **stacks:** Use distinct image tag for custom Flink build ([d300cbc](https://github.com/stefanko-ch/Nexus-Stack/commit/d300cbc1fc7346369431b32ddbf4aa7f22f6c195))


### 📚 Documentation

* **stacks:** Add BlueSky real-time streaming tutorial ([9b0ef2f](https://github.com/stefanko-ch/Nexus-Stack/commit/9b0ef2f50e2bc3f7d2d54d927ea48ee6003562c9))
* **stacks:** Document Dinky locale workaround ([ee2df2f](https://github.com/stefanko-ch/Nexus-Stack/commit/ee2df2f1a320e97ac16258b9db06ea50abf9671e))

## [0.32.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.31.2...v0.32.0) (2026-03-31)


### 🚀 Features

* **stacks:** Add Apache Flink stack + fix Control Plane env vars ([c28e1bc](https://github.com/stefanko-ch/Nexus-Stack/commit/c28e1bc3d671be740727674bb9f5e948671c800f))
* **stacks:** Add Apache Flink stream processing stack ([b058b3b](https://github.com/stefanko-ch/Nexus-Stack/commit/b058b3b77166da40188fec15be374c3a8c219c83))


### 🐛 Bug Fixes

* **ci:** Add missing env vars to wrangler.toml for Pages Functions ([d8197d8](https://github.com/stefanko-ch/Nexus-Stack/commit/d8197d8b78a505f04afc43d3d100f20a1c943064))
* **ci:** Restore Pages env vars via API after wrangler deploy ([b4ed393](https://github.com/stefanko-ch/Nexus-Stack/commit/b4ed3938a13618bec1d7f1be79cd671318cade9c))
* **ci:** Restore Pages secrets for GITHUB_OWNER, GITHUB_REPO and other vars ([953fb35](https://github.com/stefanko-ch/Nexus-Stack/commit/953fb356799944e561bff6ad9a35736a22458828))
* **stacks:** Use Docker Library flink image for ARM64 support ([1a3bd1d](https://github.com/stefanko-ch/Nexus-Stack/commit/1a3bd1ded74e1bec961ad75b7ebc614f2af792f4))

## [0.31.2](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.31.1...v0.31.2) (2026-03-30)


### 🐛 Bug Fixes

* **ci:** Address PR review comments ([39a2263](https://github.com/stefanko-ch/Nexus-Stack/commit/39a2263446f01d0eb4025ddcf695020da03ab720))
* **ci:** Fix worker secret conflicts and R2 credential error handling ([788be31](https://github.com/stefanko-ch/Nexus-Stack/commit/788be3119541f4109dcb1d798f4ebafd7e20c159))
* **ci:** Fix worker secret conflicts and R2 credential error handling ([f296e5c](https://github.com/stefanko-ch/Nexus-Stack/commit/f296e5c85eca56165da375dda2e4c146a2177b04)), closes [#279](https://github.com/stefanko-ch/Nexus-Stack/issues/279) [#280](https://github.com/stefanko-ch/Nexus-Stack/issues/280)

## [0.31.1](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.31.0...v0.31.1) (2026-03-30)


### 🐛 Bug Fixes

* **ci:** Change default server location back to fsn1 ([4c3406a](https://github.com/stefanko-ch/Nexus-Stack/commit/4c3406aacbcf7340c07eda34017a6198e8baca1f))
* **ci:** Derive Object Storage region from server hostname ([74fd3ed](https://github.com/stefanko-ch/Nexus-Stack/commit/74fd3edc1f683a1f3ff954acfb2d5b41f5886fc7))
* **ci:** Make Hetzner region configurable via SERVER_LOCATION variable ([91d88f9](https://github.com/stefanko-ch/Nexus-Stack/commit/91d88f9cbfa57601205b01b4d2574fd11bdda1cc)), closes [#278](https://github.com/stefanko-ch/Nexus-Stack/issues/278)
* **ci:** Make Hetzner server region configurable via repository variable ([b57fdc4](https://github.com/stefanko-ch/Nexus-Stack/commit/b57fdc4134c1c9bdaba6bc344b65995705f8e095))
* **ci:** Propagate HETZNER_S3_LOCATION to OpenTofu variables ([b0575dc](https://github.com/stefanko-ch/Nexus-Stack/commit/b0575dc98497cc33b5b718d133f9b22c9bc7f877))
* **ci:** Separate Object Storage region from server location ([814f24c](https://github.com/stefanko-ch/Nexus-Stack/commit/814f24cbd7755b1cb3815ca84d60708e442cf039))


### 📚 Documentation

* Add note about ARM server availability per Hetzner region ([6cd40ef](https://github.com/stefanko-ch/Nexus-Stack/commit/6cd40ef0527c6522d2a8a5fad163ae7ddad1ff12))

## [0.31.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.30.0...v0.31.0) (2026-03-30)


### 🚀 Features

* **stacks:** Add RisingWave streaming database ([cfe4862](https://github.com/stefanko-ch/Nexus-Stack/commit/cfe486238f9b6f0a7fd8da782da43f2b5f21023e))
* **stacks:** Add RisingWave streaming database ([a9d3868](https://github.com/stefanko-ch/Nexus-Stack/commit/a9d386877a04c184f1b4b0a2d3c8aad30de22534)), closes [#284](https://github.com/stefanko-ch/Nexus-Stack/issues/284)


### 🐛 Bug Fixes

* Address PR review comments for RisingWave stack ([0889d1a](https://github.com/stefanko-ch/Nexus-Stack/commit/0889d1adeb0bae8aca713672933ae3480d86440c))
* **stacks:** Connect RisingWave dashboard to Prometheus ([e3e4ca1](https://github.com/stefanko-ch/Nexus-Stack/commit/e3e4ca1b6fab1176772fd04e830e25abbb2e496a))


### 📚 Documentation

* Add missing Cloudflare setup steps to setup guide ([3e15af9](https://github.com/stefanko-ch/Nexus-Stack/commit/3e15af9f4b38a737547b21dd794a13464cc3da29))
* Add missing Cloudflare setup steps to setup guide ([2832ba1](https://github.com/stefanko-ch/Nexus-Stack/commit/2832ba11fa4db77f9ca1e7c354f6a48a9be24150))
* **stacks:** Add Prometheus monitoring info to RisingWave docs ([bde8337](https://github.com/stefanko-ch/Nexus-Stack/commit/bde833739cc14fba70c71c1654682fb62c29f27c))

## [0.30.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.29.0...v0.30.0) (2026-03-28)


### 🚀 Features

* Add R2 datalake bucket with auto-Filestash integration ([a74fd1f](https://github.com/stefanko-ch/Nexus-Stack/commit/a74fd1fb58e5a606b766ac863c087964bbf5c026))
* Add R2 datalake bucket with auto-Filestash integration ([1e53fdf](https://github.com/stefanko-ch/Nexus-Stack/commit/1e53fdf8440bbcb4444adbdd839e00d43aa7d1ee))


### 🐛 Bug Fixes

* Address remaining PR review comments ([944d63c](https://github.com/stefanko-ch/Nexus-Stack/commit/944d63c058b2912e04b5c0fcbcb63e3d2ed9a686))
* **ci:** Ensure R2 state bucket exists before tofu init and harden error handling ([1b0a3c7](https://github.com/stefanko-ch/Nexus-Stack/commit/1b0a3c7030d58fe2e9fd802608a6d8ade771fba8))
* **ci:** Gracefully handle missing R2 credentials in destroy-all ([9503182](https://github.com/stefanko-ch/Nexus-Stack/commit/950318229a1821b0954154055d0217773f79af18))
* **ci:** Keep R2 state credentials across destroy-all ([052fa46](https://github.com/stefanko-ch/Nexus-Stack/commit/052fa4644ab13ea0530b15f4a2268e7383210ce3))
* **ci:** Preserve R2 state bucket across destroy-all ([09aceec](https://github.com/stefanko-ch/Nexus-Stack/commit/09aceeca8f78bc15e9314731a8b981f575acb7c5))
* Pass R2 data credentials from setup to spin-up for first-run ([b21722e](https://github.com/stefanko-ch/Nexus-Stack/commit/b21722ea9424d7cb39a010fc8bb48ccce51d3fd0))
* Update post-startup Filestash config to include R2 as primary ([6424675](https://github.com/stefanko-ch/Nexus-Stack/commit/64246750abace19566f1d28ceaf7ae1e4b9ed9e1))

## [0.29.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.28.1...v0.29.0) (2026-03-27)


### 🚀 Features

* Add connection test and sync status to Databricks integration ([b163728](https://github.com/stefanko-ch/Nexus-Stack/commit/b163728386910f5b6886096a59e3e99cb8e0f8cb))
* Add external S3/R2 storage auto-mount for Filestash ([fd1807d](https://github.com/stefanko-ch/Nexus-Stack/commit/fd1807d77ff3d3310364b008cb6be25665ccb692)), closes [#261](https://github.com/stefanko-ch/Nexus-Stack/issues/261)
* External S3 storage, Infisical folders, and volume protection ([67fa4fd](https://github.com/stefanko-ch/Nexus-Stack/commit/67fa4fdabfafb4d60c7eb97eab2d9f42e86b1820))
* Push external S3/R2 credentials to Infisical ([368135a](https://github.com/stefanko-ch/Nexus-Stack/commit/368135a8601a5d197611ffcee353f0616f7f4ea2))
* Push Hetzner Object Storage credentials to Infisical ([cfc5fe8](https://github.com/stefanko-ch/Nexus-Stack/commit/cfc5fe8d915be375f7f03bce9b7960a262d52131))
* **stacks:** Add Python, uv, and Jupyter to code-server ([c6acbec](https://github.com/stefanko-ch/Nexus-Stack/commit/c6acbec1942b4804cbe6f3f449dc366732ce47fb))
* **stacks:** Add Python, uv, and Jupyter to code-server ([5eb9021](https://github.com/stefanko-ch/Nexus-Stack/commit/5eb9021e78ca41e45182578753f4db515da7c674))
* **stacks:** Enable Grafana anonymous access with Viewer role ([6cb3aa8](https://github.com/stefanko-ch/Nexus-Stack/commit/6cb3aa817c0a835365913d92646bdbe7438266c6)), closes [#233](https://github.com/stefanko-ch/Nexus-Stack/issues/233)
* **stacks:** Grafana anonymous access (skip double login) ([7304255](https://github.com/stefanko-ch/Nexus-Stack/commit/73042551bfddc6fdd5fe5c46fa9ad0afb93d04e4))
* Sync Infisical secrets to Databricks Secret Scopes ([8182a7b](https://github.com/stefanko-ch/Nexus-Stack/commit/8182a7bbb136edef1d7c423d39066e3d942fa8a8)), closes [#175](https://github.com/stefanko-ch/Nexus-Stack/issues/175)
* Sync Infisical secrets to Databricks via Control Panel ([12fa194](https://github.com/stefanko-ch/Nexus-Stack/commit/12fa19448594e1b3d54e68704f4d0d53c33e7e35))


### 🐛 Bug Fixes

* Add --delete to rsync and guard empty Infisical token ([2b8e4dc](https://github.com/stefanko-ch/Nexus-Stack/commit/2b8e4dc35975239ea8e118af0f5d35b0652dcc6d))
* Add KV namespace binding to wrangler.toml for Pages deploy ([c4063b0](https://github.com/stefanko-ch/Nexus-Stack/commit/c4063b06b16f5b91d96672211efa295502b906ca))
* Address all PR review comments for Databricks sync ([41a3d68](https://github.com/stefanko-ch/Nexus-Stack/commit/41a3d68ebedadb4ef72ed8ad151a58e6ca5f4317))
* Address PR review — connection test, poll, and error handling ([10d9c6a](https://github.com/stefanko-ch/Nexus-Stack/commit/10d9c6acd97181e92073d2c3c9ff48ebc870e399))
* Address PR review — guard empty S3 secrets, default region ([524fd6b](https://github.com/stefanko-ch/Nexus-Stack/commit/524fd6be7aac763cf0360c4b9146960b4e44f925))
* **ci:** Add KV binding to spin-up Pages redeploy ([6759a70](https://github.com/stefanko-ch/Nexus-Stack/commit/6759a700cf5226e02c4173a937686325ede61287))
* **ci:** Add retry for Cloudflare Pages deploy (504 timeouts) ([00d152a](https://github.com/stefanko-ch/Nexus-Stack/commit/00d152a43bffe8aade32501a78ce5fdbeeafbee7))
* **ci:** Add retry logic for Cloudflare Pages deploy (504 timeouts) ([bc64413](https://github.com/stefanko-ch/Nexus-Stack/commit/bc64413c539e54d154879e8781fb76d5edb4f495))
* **ci:** Delete R2 bucket before revoking R2 API token ([08dca5b](https://github.com/stefanko-ch/Nexus-Stack/commit/08dca5bf8eabe173307cff3c3a588f6993b7a339))
* **ci:** Import existing S3 buckets instead of deleting them ([1e9c803](https://github.com/stefanko-ch/Nexus-Stack/commit/1e9c8036194d2ff5ab89d20ace75bdf009d17d28))
* **ci:** Init both control-plane and stack state in databricks-sync ([7284e67](https://github.com/stefanko-ch/Nexus-Stack/commit/7284e6743108aadd506f8dcb362268a28e62b67e))
* **ci:** Pin wrangler to [@4](https://github.com/4) instead of [@latest](https://github.com/latest) ([247cdf8](https://github.com/stefanko-ch/Nexus-Stack/commit/247cdf8ee0e60bf080044572123ea79549ec1b70))
* **ci:** Pin wrangler to major version 4 instead of [@latest](https://github.com/latest) ([962495e](https://github.com/stefanko-ch/Nexus-Stack/commit/962495e67356bac91f424bdb0cc191efe351f03c))
* **ci:** Place shellcheck disable directly before each ssh line ([b5f2854](https://github.com/stefanko-ch/Nexus-Stack/commit/b5f28547051518bbbb51fb9d48161e62694c1c71))
* **ci:** Pre-create Hetzner S3 buckets to avoid provider ACL error ([d716ffe](https://github.com/stefanko-ch/Nexus-Stack/commit/d716ffe01a2e762299d2e5de2383efaaed421784))
* **ci:** Prevent set -e from killing script on aws bucket creation failure ([9fb9c75](https://github.com/stefanko-ch/Nexus-Stack/commit/9fb9c754a36514730d36ac81f3c71f1139c81279))
* **ci:** Replace A && B || C pattern with proper if-else ([eaa5ff4](https://github.com/stefanko-ch/Nexus-Stack/commit/eaa5ff42dce953598bc4b297f92b4cde297dc249))
* **ci:** Show actual error when bucket pre-creation fails ([7c42343](https://github.com/stefanko-ch/Nexus-Stack/commit/7c42343016485a807c6ca5638a0da64e65388214))
* **ci:** Suppress SC2029 in databricks-sync (intentional local expansion) ([2d61b92](https://github.com/stefanko-ch/Nexus-Stack/commit/2d61b922ef014bee67ed8f03bdee7ce2a78676fc))
* **ci:** Suppress shellcheck warnings in databricks-sync workflow ([cc0665e](https://github.com/stefanko-ch/Nexus-Stack/commit/cc0665e9caa806a62f084c9ec9f3f70c60ac1cc4))
* **ci:** Use accountID/namespaceID format for KV import ([38af6b4](https://github.com/stefanko-ch/Nexus-Stack/commit/38af6b4618a513053154199946bba0ac538c614f))
* **ci:** Use accountID/namespaceID format for KV import ([2cbc3c0](https://github.com/stefanko-ch/Nexus-Stack/commit/2cbc3c0ad16f7a5ef46fc4244a4fd888ca0f7c78))
* Databricks sync fixes, connection test, and status polling ([f724f2a](https://github.com/stefanko-ch/Nexus-Stack/commit/f724f2a794040892c26fd1c860f36e7cf42e0ba8))
* Merge read+push steps (trap EXIT deleted file) and use 24h time ([2ba10f0](https://github.com/stefanko-ch/Nexus-Stack/commit/2ba10f09137a671237ae33ec23e6cf39c64e69da))
* Only retry on 504 timeouts, use ISO timestamp for sync status ([253fb62](https://github.com/stefanko-ch/Nexus-Stack/commit/253fb620a43bffd5a4f92c9aa3ed865d8c3657ac))
* Protect persistent volume from destroy-all ([6a40dad](https://github.com/stefanko-ch/Nexus-Stack/commit/6a40dadab1cd04bf41561adee3bf2392d1976368))
* Protect S3 buckets from destroy-all and use single Databricks scope ([8fb7625](https://github.com/stefanko-ch/Nexus-Stack/commit/8fb762513967f744fd5e8480295612735743f25e))
* Protect S3 buckets from destroy-all, single Databricks scope ([5000b53](https://github.com/stefanko-ch/Nexus-Stack/commit/5000b53eebe2a649c3c2283c16285b60d2394678))
* Read secrets from OpenTofu state for Databricks sync ([d083b5f](https://github.com/stefanko-ch/Nexus-Stack/commit/d083b5f9178cbd66fb0639f28f274c8e4a9c885d))
* Read secrets from OpenTofu state instead of Infisical API ([019bfc0](https://github.com/stefanko-ch/Nexus-Stack/commit/019bfc0ed8721977b9381cc70dd2809b17219761))
* Remove secret values from debug output, show only keys/count ([0574000](https://github.com/stefanko-ch/Nexus-Stack/commit/0574000aa4b4a8a2ea6187500e02e2bb3262b2cd))
* Rename hetzner_s3_bucket to hetzner_s3_bucket_lakefs in secrets output ([68fff6b](https://github.com/stefanko-ch/Nexus-Stack/commit/68fff6b0105b6b03d5695b5675c68a7eb7a67686))
* Secure temp file permissions and use printf for secret values ([bc3a239](https://github.com/stefanko-ch/Nexus-Stack/commit/bc3a2397cc748aca6565de9ff4564d9f463e6597))
* Skip sleep after final retry attempt, fix deploy log messages ([3e77a0c](https://github.com/stefanko-ch/Nexus-Stack/commit/3e77a0c8bda6bc9c692de73e3437646566e3ac99))
* **stacks:** Add env_file and anonymous access to CloudBeaver ([7da00f2](https://github.com/stefanko-ch/Nexus-Stack/commit/7da00f21d7b539b834d06bce89b35ed18896fdca))
* **stacks:** Address PR review — pin versions, restore image override ([bfcb46b](https://github.com/stefanko-ch/Nexus-Stack/commit/bfcb46b8829d97a21cadef393a3439fc8b6837b8))
* **stacks:** Auto-configure CloudBeaver to skip initial setup wizard ([dc5b549](https://github.com/stefanko-ch/Nexus-Stack/commit/dc5b5490d94b0a39f984fccd8e180c42e124f583))
* **stacks:** Fix CloudBeaver env_file and enable anonymous access ([458177d](https://github.com/stefanko-ch/Nexus-Stack/commit/458177d42ec9d05768706e967356be9e0d537269))
* **stacks:** Use jupyterlab package for uv tool install ([490ed12](https://github.com/stefanko-ch/Nexus-Stack/commit/490ed12968acc8a381c74669d15cff2f4197e923))


### ♻️ Refactoring

* Reorganize Infisical secrets into folders with idempotent push ([891ddc3](https://github.com/stefanko-ch/Nexus-Stack/commit/891ddc38bab920f4631bd5359453b59c41c163f5))


### 🔧 Maintenance

* **ci:** Update GitHub Actions from Node.js 20 to Node.js 24 ([6e60511](https://github.com/stefanko-ch/Nexus-Stack/commit/6e605110cf81a4f8294b9228c1f1aed5c022137d))
* **ci:** Update GitHub Actions to Node.js 24 ([4f8f8c3](https://github.com/stefanko-ch/Nexus-Stack/commit/4f8f8c3545fedc691f65745c75bd6088c742c5e3)), closes [#251](https://github.com/stefanko-ch/Nexus-Stack/issues/251)

## [0.28.1](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.28.0...v0.28.1) (2026-03-23)


### 🐛 Bug Fixes

* Add admin link to info panel and fix Filestash password ([45e712b](https://github.com/stefanko-ch/Nexus-Stack/commit/45e712b5243e0ce557c040be23d8396181d696a2))
* Address PR review comments ([39b0766](https://github.com/stefanko-ch/Nexus-Stack/commit/39b076607e0ce1f4939877b624aa35608a3b2347))
* **stacks:** Fix MinIO image tag and Filestash admin password ([f9c041a](https://github.com/stefanko-ch/Nexus-Stack/commit/f9c041adb9df134516331fd80505b308f3df3b29))
* **stacks:** Update MinIO image to valid quay.io tag ([3085caf](https://github.com/stefanko-ch/Nexus-Stack/commit/3085caf53851f60ccea28ec2d18514ef8d1f1c28))

## [0.28.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.27.1...v0.28.0) (2026-03-03)


### 🚀 Features

* **control-plane:** Add email notification toggles ([98d6021](https://github.com/stefanko-ch/Nexus-Stack/commit/98d6021b4c1fd70560dea1c4d6c81eb204223280))
* **control-plane:** Add Silent Mode to suppress automated emails ([1e93a44](https://github.com/stefanko-ch/Nexus-Stack/commit/1e93a44cd2a4c05f29074289688f3d0af5725f06)), closes [#242](https://github.com/stefanko-ch/Nexus-Stack/issues/242)
* **control-plane:** Email notification toggles and Silent Mode ([6758583](https://github.com/stefanko-ch/Nexus-Stack/commit/675858369e23281e8591f2ed1bbe401450d55337))
* **control-plane:** Show silent mode state in email toggles UI ([c006faa](https://github.com/stefanko-ch/Nexus-Stack/commit/c006faa097d92df092fcaf9b3f2a63b1b1aa1ccc))
* **stacks:** Add optional workspace Git repo fork with custom naming ([1c01444](https://github.com/stefanko-ch/Nexus-Stack/commit/1c01444457374ab4c0d6fe4a672689b0915c6fa7))
* **stacks:** Add workspace Git repo fork from GitHub mirror ([f7afb7a](https://github.com/stefanko-ch/Nexus-Stack/commit/f7afb7afb571ab8bd578b4a5f299a2071ed40f7e))


### 🐛 Bug Fixes

* **ci:** Handle tainted Hetzner buckets in cleanup step ([22dd450](https://github.com/stefanko-ch/Nexus-Stack/commit/22dd45018279498a01b22375aef9bacfb92b4d10))
* **control-plane:** Address Copilot review comments on email-settings API ([e596176](https://github.com/stefanko-ch/Nexus-Stack/commit/e596176487e101407590f03ed93a6f0c41f02913))
* **stacks:** Address PR review comments ([e3f7f1d](https://github.com/stefanko-ch/Nexus-Stack/commit/e3f7f1d0a051ae80b5979ed0de9e859b54a62064))
* **stacks:** Fix Jupyter crash due to nounset flag in sourced hook ([f3e3fa3](https://github.com/stefanko-ch/Nexus-Stack/commit/f3e3fa38b34ba35c0d88da16e2633c26fd1a289e))
* **stacks:** Fix Jupyter crash due to nounset flag in sourced hook ([c6f3142](https://github.com/stefanko-ch/Nexus-Stack/commit/c6f3142addf66bafefc33f8277e0ba5c69c500a3))
* **stacks:** Fork workspace repo after mirror is created, not before ([e8d8fd7](https://github.com/stefanko-ch/Nexus-Stack/commit/e8d8fd70d712e205eb27c0403f812883bfed88ba))
* **stacks:** Fork workspace repo even when mirror already exists ([c3e057c](https://github.com/stefanko-ch/Nexus-Stack/commit/c3e057c2a681af5485ab975a2c8d251a36c438c4))
* **stacks:** Restart git services after fork, not before ([11db7de](https://github.com/stefanko-ch/Nexus-Stack/commit/11db7de77129f4ecec04b4b8f247764aa74b19e8))
* **stacks:** Save/restore shell options in sourced Jupyter hook ([1bbeb22](https://github.com/stefanko-ch/Nexus-Stack/commit/1bbeb221631bca1634751387d029cad3033481a0))
* **tofu:** Pin minio provider to v3.20.0 ([5658e58](https://github.com/stefanko-ch/Nexus-Stack/commit/5658e587973989ea9ba89307b4b435b746db6be5))


### ♻️ Refactoring

* **stacks:** Derive workspace repo from GH_MIRROR_REPOS automatically ([94ab49b](https://github.com/stefanko-ch/Nexus-Stack/commit/94ab49ba9e2a8f19efe3a57cfa788d1a33907255))
* **stacks:** Simplify WORKSPACE_GIT_REPO to plain repo name ([c363ccd](https://github.com/stefanko-ch/Nexus-Stack/commit/c363ccd18fc1653e2e853c8dfd3128e58b5bfcc5))

## [0.27.1](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.27.0...v0.27.1) (2026-02-19)


### 🐛 Bug Fixes

* **ci:** Separate R2 and Hetzner credentials in bucket cleanup step ([67b7506](https://github.com/stefanko-ch/Nexus-Stack/commit/67b750686f543926675841db0e14966fcbe7c1a9))
* **tofu:** Fix Hetzner Object Storage bucket ACL error on re-deploy ([9ca1b23](https://github.com/stefanko-ch/Nexus-Stack/commit/9ca1b236bbc322ba9981c0eb59ee37d2820c993b))
* **tofu:** Fix Hetzner Object Storage bucket ACL error on re-deploy ([97df4db](https://github.com/stefanko-ch/Nexus-Stack/commit/97df4dba3a6d3e34b8c9f05bf4dce169c553e44c))

## [0.27.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.26.0...v0.27.0) (2026-02-19)


### 🚀 Features

* **stacks:** Add Ollama + Open WebUI stack ([01bc881](https://github.com/stefanko-ch/Nexus-Stack/commit/01bc881319cb8a63caa1342e6f6b2f4516a6585f))
* **stacks:** Add Ollama + Open WebUI stack ([5e798ea](https://github.com/stefanko-ch/Nexus-Stack/commit/5e798ea68ddc50ce768c8a2064a36393cb144e1a)), closes [#217](https://github.com/stefanko-ch/Nexus-Stack/issues/217)
* **stacks:** Add optional GitHub-to-Gitea repository mirroring ([9f3bc26](https://github.com/stefanko-ch/Nexus-Stack/commit/9f3bc26e61dff7884b62dc2c0c120769f0b55b7b))
* **stacks:** Add optional GitHub→Gitea repository mirroring ([73e2510](https://github.com/stefanko-ch/Nexus-Stack/commit/73e25108aef3cf5e97bfa90457e5b55142e460d7))
* **ui:** Show release version in Control Panel and Info page header ([f4fe1e5](https://github.com/stefanko-ch/Nexus-Stack/commit/f4fe1e583050d5bf8797af5de938d5ee5df3dccd))


### 🐛 Bug Fixes

* **ci:** Handle R2 credential validation failure gracefully ([e6935c8](https://github.com/stefanko-ch/Nexus-Stack/commit/e6935c81d1d22dbaa1c85f8b810f273f13e4309a))
* **ci:** Stop swallowing tofu init errors in destroy workflow ([6f1bf2c](https://github.com/stefanko-ch/Nexus-Stack/commit/6f1bf2c185e01e22851d7e9c09a954ff61055bde))
* **control-plane:** Address PR review comments ([3da99ee](https://github.com/stefanko-ch/Nexus-Stack/commit/3da99eeb20625661a18ad00c12dfd140e295b798))
* **control-plane:** Fix pending changes race condition and improve UX ([63fdbb0](https://github.com/stefanko-ch/Nexus-Stack/commit/63fdbb08f8cbdbed091dd5d6383393052b71b32a))
* **control-plane:** Fix pending changes UX and CI error handling ([280b243](https://github.com/stefanko-ch/Nexus-Stack/commit/280b2432ddbe7e6d99dd46f49be5c00c86fb4595))
* **control-plane:** Return 'destroyed' instead of 'offline' from status API ([37d78ee](https://github.com/stefanko-ch/Nexus-Stack/commit/37d78eef98113d3df62da771edbf39ab92276266))
* **stacks:** Address PR review comments for mirror feature ([e08c1b6](https://github.com/stefanko-ch/Nexus-Stack/commit/e08c1b638b3639faf78974e2317cd035f10395c6))
* **stacks:** Disable must-change-password on Gitea password sync ([1c7c661](https://github.com/stefanko-ch/Nexus-Stack/commit/1c7c661cfdd64f9e1c90d069b9ce713723f18cac))
* **stacks:** Fix mirror creation by piping jq payload via stdin ([d959f08](https://github.com/stefanko-ch/Nexus-Stack/commit/d959f089f1043572794ddf7e68050d65a826bf4b))
* **stacks:** Pipe jq payload via stdin to fix SSH variable passing ([165a95f](https://github.com/stefanko-ch/Nexus-Stack/commit/165a95f151708b8b58a51be57e9d98b23f66efb8))
* **stacks:** Rename mirror secrets to avoid reserved GITHUB_ prefix ([b54ed9b](https://github.com/stefanko-ch/Nexus-Stack/commit/b54ed9bb37d928f81d281f266c86d58ec67494eb))
* **stacks:** Sync Gitea admin and user passwords on spin-up ([23e6bfb](https://github.com/stefanko-ch/Nexus-Stack/commit/23e6bfbc99969b7992ca69cb8541e527df07bf56))
* **stacks:** Sync Gitea DB password on spin-up to handle persistent volume state mismatch ([00152e9](https://github.com/stefanko-ch/Nexus-Stack/commit/00152e9d13264811257d1d54e933844f1764625e))
* **stacks:** Use default expansion for GITEA_TOKEN to avoid unbound variable error ([a819bcf](https://github.com/stefanko-ch/Nexus-Stack/commit/a819bcf4455320903b239c43f172c025e56d6c9c))
* **stacks:** Use latest tag for drawio Docker image ([e7c2f2e](https://github.com/stefanko-ch/Nexus-Stack/commit/e7c2f2eb8ed213e8d51940b2b6b17f73c924e34a))
* **stacks:** Use ollama CLI for healthcheck instead of curl ([dfa4d24](https://github.com/stefanko-ch/Nexus-Stack/commit/dfa4d24ae63cc6d6ae5e2975c0305de4662e3ea8))
* **stacks:** Use printf instead of echo for JSON payload piping ([986d502](https://github.com/stefanko-ch/Nexus-Stack/commit/986d5025fe38595c4828782a5445a26673af9473))


### 📚 Documentation

* Add critical review guideline for Copilot PR comments ([91186a0](https://github.com/stefanko-ch/Nexus-Stack/commit/91186a0b2a9b7209602457873089f95fc29ddec6))
* Add Git Desktop to git-proxy description ([ff00f66](https://github.com/stefanko-ch/Nexus-Stack/commit/ff00f660621b368743a50ba56a3107e9933dd28b))
* **stacks:** Clarify exact PAT permissions for GitHub mirror ([9b430cf](https://github.com/stefanko-ch/Nexus-Stack/commit/9b430cf3c7b869d94f82225a4877a7e13f459ff1))
* **stacks:** Clarify mirror skip condition wording ([2ae7d66](https://github.com/stefanko-ch/Nexus-Stack/commit/2ae7d66f90132f80baad3a8100e4690183dba7c8))
* **stacks:** Expand Ollama docs with CPU-only note and model guide ([af64bf3](https://github.com/stefanko-ch/Nexus-Stack/commit/af64bf33fdff85ec73525a8af8107bc63e98f866))
* **stacks:** Recommend fine-grained PAT for GitHub mirror setup ([53158ef](https://github.com/stefanko-ch/Nexus-Stack/commit/53158ef7f159213ca9b02353bda7624b33c1c4fa))

## [0.26.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.25.0...v0.26.0) (2026-02-15)


### 🚀 Features

* **stacks:** Add Dify AI workflow builder platform ([a0b5546](https://github.com/stefanko-ch/Nexus-Stack/commit/a0b5546a6a44f57de963517a50af35224ff94f34))
* **stacks:** Add Dify AI workflow builder platform ([4fe76ab](https://github.com/stefanko-ch/Nexus-Stack/commit/4fe76ab2a443ac671ccb447382957e1b6d86bbc1)), closes [#220](https://github.com/stefanko-ch/Nexus-Stack/issues/220)
* **stacks:** Make Grafana a core service for always-on monitoring ([e63beda](https://github.com/stefanko-ch/Nexus-Stack/commit/e63bedab39ce6962ba26f79ab8c4d332f7e180b5))


### 🐛 Bug Fixes

* **scripts:** Fix Dify auto-setup and storage permissions ([3e57ab4](https://github.com/stefanko-ch/Nexus-Stack/commit/3e57ab40d91e62e9f951b04e76932e34d7d566a3))
* **scripts:** Fix variable expansion for Dify storage chown ([c6cf877](https://github.com/stefanko-ch/Nexus-Stack/commit/c6cf8770cc82c1ad3632b398fa3be67dc8a6cc91))
* **stacks:** Add missing plugin daemon env vars and nginx depends_on ([48d7f86](https://github.com/stefanko-ch/Nexus-Stack/commit/48d7f86b7683c6d196d16139134acffd07ab1d59))
* **stacks:** Add Redis config to Dify plugin daemon ([08de791](https://github.com/stefanko-ch/Nexus-Stack/commit/08de7910eba8d9c0d5a8ef7c4e755b85d1735ea5))
* **stacks:** Address PR review comments for Dify stack ([4d4857e](https://github.com/stefanko-ch/Nexus-Stack/commit/4d4857e148f2922853bfa0f3170a341feb9ed7db))
* **stacks:** Enable Dify database migrations on startup ([68c32b4](https://github.com/stefanko-ch/Nexus-Stack/commit/68c32b4ee7b9ac668d555746368bd498cd674fd5))
* **stacks:** Fix Dify nginx healthcheck for 307 redirect ([68f8a99](https://github.com/stefanko-ch/Nexus-Stack/commit/68f8a9994b0177fa1ebc063c6792e048cf8e8daa))
* **stacks:** Rename dify-nginx container to dify for deploy.sh health check ([e90abee](https://github.com/stefanko-ch/Nexus-Stack/commit/e90abee0827fdf898902de887d909f4a2dccf947))

## [0.25.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.24.0...v0.25.0) (2026-02-14)


### 🚀 Features

* **stacks:** Add NocoDB open-source Airtable alternative ([135f5b5](https://github.com/stefanko-ch/Nexus-Stack/commit/135f5b5bd6624129f36704f7aad7bca7e262cee4))
* **stacks:** Add Quickwit cloud-native log search engine ([23d3c82](https://github.com/stefanko-ch/Nexus-Stack/commit/23d3c8295d3eacbb7be4facd6cfec2e0384dea2b))
* **stacks:** Add Quickwit log search and NocoDB Airtable alternative ([302a515](https://github.com/stefanko-ch/Nexus-Stack/commit/302a5154cfc7761c21508ba7c7969c2e180f8a75))


### 🐛 Bug Fixes

* **docs:** Add missing Draw.io documentation and README entry ([91c8867](https://github.com/stefanko-ch/Nexus-Stack/commit/91c8867ae20c533465b96fb8cc4b69fb6a64720c))
* **docs:** Address PR [#223](https://github.com/stefanko-ch/Nexus-Stack/issues/223) review comments ([0965be7](https://github.com/stefanko-ch/Nexus-Stack/commit/0965be73b1f956ad5cb119d893a33cc4696e2527))
* **scripts:** Add NocoDB JWT secret to Infisical and validate .env generation ([3543c91](https://github.com/stefanko-ch/Nexus-Stack/commit/3543c91aa51bbe4e0efcaa15401ac1db1149c6e7))
* **scripts:** Fix Infisical secrets push JSON parse error ([9b89c4a](https://github.com/stefanko-ch/Nexus-Stack/commit/9b89c4accc91541deb3faa605137e40473c28f1e))
* **scripts:** Fix invalid JSON in Infisical secrets payload ([04bf37b](https://github.com/stefanko-ch/Nexus-Stack/commit/04bf37b7c283b6d60b7aaec109935f77f85ad984))
* **scripts:** Use correct Infisical v3 batch API endpoint ([a7e28a6](https://github.com/stefanko-ch/Nexus-Stack/commit/a7e28a65cb673a5e94bc351748e1eb5f27527c73))
* **stacks:** Address PR review comments for Quickwit and NocoDB ([1f431a4](https://github.com/stefanko-ch/Nexus-Stack/commit/1f431a4f106dac4212172327761e674151b66a23))
* **stacks:** Complete Quickwit and NocoDB integration ([9915326](https://github.com/stefanko-ch/Nexus-Stack/commit/991532698b64984f805a30e96d4c923e7535649a))
* **stacks:** Use correct NC_DB connection string format for NocoDB ([53618fe](https://github.com/stefanko-ch/Nexus-Stack/commit/53618fe390afad1d24729ef50f0cc1c36084b7a3))


### ♻️ Refactoring

* **docs:** Split stacks.md into individual per-stack files ([f639bb3](https://github.com/stefanko-ch/Nexus-Stack/commit/f639bb39bd0922e5294655ed04cd4663dc82d6e1))
* **docs:** Split stacks.md into individual per-stack files ([e14ffe6](https://github.com/stefanko-ch/Nexus-Stack/commit/e14ffe6976f519c048d3c9cf09c98eadac53f737))


### 📚 Documentation

* Add one-branch-at-a-time rule to CLAUDE.md ([344f9b6](https://github.com/stefanko-ch/Nexus-Stack/commit/344f9b6322d75fe03f279598ddc93edabb911f65))


### 🔧 Maintenance

* Remove outdated make command references ([6f07a46](https://github.com/stefanko-ch/Nexus-Stack/commit/6f07a4681b3224ffc00d9252d27ca9163b5fd5f5))

## [0.24.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.23.0...v0.24.0) (2026-02-13)


### 🚀 Features

* **stacks:** Add S3 Manager web UI for object storage ([9c360dd](https://github.com/stefanko-ch/Nexus-Stack/commit/9c360ddecf1fe65aaf63307ef9e51ed441ad27a7))
* **stacks:** Add S3 Manager web UI for object storage ([51a66eb](https://github.com/stefanko-ch/Nexus-Stack/commit/51a66eb90621de690255fd1d5bcb36289772dc53)), closes [#215](https://github.com/stefanko-ch/Nexus-Stack/issues/215)


### 🐛 Bug Fixes

* **stacks:** Remove https:// prefix from S3 Manager endpoint ([e1c0227](https://github.com/stefanko-ch/Nexus-Stack/commit/e1c0227c850e5ff11d496d14e94a1deba491b044))
* **stacks:** Rename s3manager subdomain and add missing REGION env var ([3e6a92c](https://github.com/stefanko-ch/Nexus-Stack/commit/3e6a92c2e9d264725881f0e459e8aea23d17281b))
* **tofu:** Add force_destroy to Hetzner Object Storage buckets ([21bb02d](https://github.com/stefanko-ch/Nexus-Stack/commit/21bb02db23220df4cce1be467f20fac5104a6e76))


### 📚 Documentation

* Add stack count to Available Stacks heading ([23de0e6](https://github.com/stefanko-ch/Nexus-Stack/commit/23de0e614a023fa3b9f116f26947bb8c10eef1b2))


### 🔧 Maintenance

* Remove Co-Authored-By trailers from commit convention ([f466899](https://github.com/stefanko-ch/Nexus-Stack/commit/f46689924609e63b9c8f00718cec236191d0548c))

## [0.23.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.22.0...v0.23.0) (2026-02-13)


### 🚀 Features

* **stacks:** Add Apache Spark cluster and upgrade Jupyter to PySpark ([c8dd883](https://github.com/stefanko-ch/Nexus-Stack/commit/c8dd8839220023cb15ef8be5217ced5a3f1bf9a4))
* **stacks:** Add Apache Spark cluster with PySpark Jupyter integration ([a4e5cae](https://github.com/stefanko-ch/Nexus-Stack/commit/a4e5cae6879b01a031d196afef4cd9040e3378ee))
* **stacks:** Add dedicated PySpark kernel to Jupyter ([d6f74a8](https://github.com/stefanko-ch/Nexus-Stack/commit/d6f74a8a667441fbc785898806e89e6b947f425f))
* **stacks:** Add Docker resource limits to Spark containers ([a35013e](https://github.com/stefanko-ch/Nexus-Stack/commit/a35013ed3539a4148144dae8fc80d71ab0ff94b1))
* **stacks:** Add PySpark starter notebook to Jupyter ([018c7f4](https://github.com/stefanko-ch/Nexus-Stack/commit/018c7f42688b9e332c56345b59cf0a7c6468839f))
* **stacks:** Add S3 bucket access to Spark/Jupyter starter notebook ([639c4d1](https://github.com/stefanko-ch/Nexus-Stack/commit/639c4d1eb19561829eebdb2ee70b02c2e0b25fb0))


### 🐛 Bug Fixes

* **ci:** Address PR review comments for persistent_volume_id validation ([963cef5](https://github.com/stefanko-ch/Nexus-Stack/commit/963cef5ba5ff9e372ec44f01c2a273cfd0cbfec2))
* **ci:** Address PR review comments for R2 token cleanup ([6c37465](https://github.com/stefanko-ch/Nexus-Stack/commit/6c37465fd105dae371d6adaef18b0f64aaf05ca3))
* **ci:** Scope R2 token deletion to own deployment only ([4d54b24](https://github.com/stefanko-ch/Nexus-Stack/commit/4d54b24e27ed5b379534940a69dc76125dcd477b))
* **ci:** Scope R2 token deletion to own deployment only ([ebd0f3b](https://github.com/stefanko-ch/Nexus-Stack/commit/ebd0f3b72e09095752a2a98bec920b5d2a5c6453))
* **ci:** Validate persistent_volume_id before writing to tfvars ([5001502](https://github.com/stefanko-ch/Nexus-Stack/commit/5001502f619abfe19c9ebf23c0bd26d30d04156d))
* **ci:** Validate persistent_volume_id before writing to tfvars ([2e1ada8](https://github.com/stefanko-ch/Nexus-Stack/commit/2e1ada809dea5b5195ba0774dd250312536505d3))
* **stacks:** Add hadoop-aws and AWS SDK v2 JARs for S3A support ([698411d](https://github.com/stefanko-ch/Nexus-Stack/commit/698411d8c5bd79aff160b0d8b45012c414a2199a))
* **stacks:** Add PYTHONPATH for PySpark in Jupyter container ([02dbbf9](https://github.com/stefanko-ch/Nexus-Stack/commit/02dbbf9bcf96b3ff967e42202a64e550a59a1225))
* **stacks:** Address PR review comments for Spark stack ([97d9b62](https://github.com/stefanko-ch/Nexus-Stack/commit/97d9b62dc7df9422d3819005abe6d85ea1d976da))
* **stacks:** Always overwrite starter notebook on Jupyter startup ([0bf6585](https://github.com/stefanko-ch/Nexus-Stack/commit/0bf658588b247e2dd7111629e4b6d81c18b686df))
* **stacks:** Bind Spark master/worker to all network interfaces ([b31b573](https://github.com/stefanko-ch/Nexus-Stack/commit/b31b573e5698a6de3643af404e8fd9d9851f320c))
* **stacks:** Build custom Spark image with Python 3.13 to match Jupyter ([ff46bce](https://github.com/stefanko-ch/Nexus-Stack/commit/ff46bcee0a21207a524e86e1a30637409ab42858))
* **stacks:** Inject spark/sc into IPython user namespace ([53bf02b](https://github.com/stefanko-ch/Nexus-Stack/commit/53bf02bca430afc0ccf00f46043b89ebdcc544d6))
* **stacks:** Move PySpark kernel config to standalone files ([dd0c7ea](https://github.com/stefanko-ch/Nexus-Stack/commit/dd0c7ea004e17643ed9fd6dcd3de4e5c17246413))
* **stacks:** Remove duplicate build directive from Spark worker ([02a43bb](https://github.com/stefanko-ch/Nexus-Stack/commit/02a43bbf3df4b32677f9a78c67ba0857b56c0916))
* **stacks:** Remove Spark worker volume to fix executor permissions ([9253b9c](https://github.com/stefanko-ch/Nexus-Stack/commit/9253b9cc0e049f122acaee08d4f0915a4903996d))
* **stacks:** Rename spark-master container to spark for deploy verification ([bf3ac7f](https://github.com/stefanko-ch/Nexus-Stack/commit/bf3ac7f9d622c97bc0e9c7eb15425bb02bddef54))
* **stacks:** Replace curl healthcheck with bash /dev/tcp for Spark ([de43e67](https://github.com/stefanko-ch/Nexus-Stack/commit/de43e6700fa631befd1a44f7b5052212337588e7))
* **stacks:** Run Spark Master/Worker in foreground via spark-class ([fa66380](https://github.com/stefanko-ch/Nexus-Stack/commit/fa66380e36f9ad7f7fa3ce6e6a13fa4fb817c7ed))
* **stacks:** Use before-notebook.d hook for S3A JARs and rebuild on deploy ([b6c6465](https://github.com/stefanko-ch/Nexus-Stack/commit/b6c646522f11991c9d9548813c620e80738c44ec))
* **stacks:** Use correct kernel path for pyspark-notebook image ([1d3c570](https://github.com/stefanko-ch/Nexus-Stack/commit/1d3c57007a564feb06871c9cf9aa8c68c800e421))


### 📚 Documentation

* **stacks:** Mention S3A JARs in Spark custom image note ([9497af8](https://github.com/stefanko-ch/Nexus-Stack/commit/9497af81d81498c98e30158be5a51103d36b5e40))

## [0.22.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.21.0...v0.22.0) (2026-02-11)


### 🚀 Features

* **control-plane:** Add admin_only flag to prevent users from toggling Wetty ([a008e9c](https://github.com/stefanko-ch/Nexus-Stack/commit/a008e9cf1381d9e34d7ad7d9683c2226cb51f277))
* **stacks:** Add Woodpecker CI stack ([ff0155d](https://github.com/stefanko-ch/Nexus-Stack/commit/ff0155d3d89d42cb55d930a48f41c04803e1a3b9))
* **stacks:** Add Woodpecker CI stack ([5b79872](https://github.com/stefanko-ch/Nexus-Stack/commit/5b79872bb3bb7f71235dad54a1ed5c76fe10ed6e))


### 🐛 Bug Fixes

* Address second round of PR review comments ([6dcbe24](https://github.com/stefanko-ch/Nexus-Stack/commit/6dcbe24370c8225e0e1f89f877e87a95922a186e))
* **stacks:** Address PR review comments for Woodpecker stack ([50d8da2](https://github.com/stefanko-ch/Nexus-Stack/commit/50d8da2acf6f0451f2e5f899f10e0a44fec2222b))
* **stacks:** Integrate Woodpecker CI with Gitea forge ([6a50bcc](https://github.com/stefanko-ch/Nexus-Stack/commit/6a50bcccfd1b8bf6248768601330bb0a0e726022))
* **stacks:** Remove custom healthcheck from Woodpecker server ([9eb5d16](https://github.com/stefanko-ch/Nexus-Stack/commit/9eb5d1696859a6ffac7b5ef6d2561506706520b7))
* **stacks:** Split Woodpecker Gitea URL into internal API + public OAuth ([4bbec4f](https://github.com/stefanko-ch/Nexus-Stack/commit/4bbec4ff7d291c900d9132539fd4930416860f1f))
* **stacks:** Use correct v3 env var for Woodpecker OAuth redirect ([01b542d](https://github.com/stefanko-ch/Nexus-Stack/commit/01b542d95f6b37c43cca2f763b565cfc2ecb2263))
* **stacks:** Use public Gitea URL for Woodpecker OAuth and make Gitea core ([cd19fc0](https://github.com/stefanko-ch/Nexus-Stack/commit/cd19fc0dec379aa195e7b72c73c3be8d2b32ec9d))


### 📚 Documentation

* Enforce logs-first debugging approach in CLAUDE.md ([8556b7f](https://github.com/stefanko-ch/Nexus-Stack/commit/8556b7f42cf2b96cbcbd010d88aef2d7a4cf3e8e))

## [0.21.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.20.0...v0.21.0) (2026-02-11)


### 🚀 Features

* **stacks:** Add Wiki.js knowledge base stack ([a741e08](https://github.com/stefanko-ch/Nexus-Stack/commit/a741e08f50b33affe474184115730398a82df823))
* **stacks:** Add Wiki.js stack + CI/CD resilience fixes ([1612409](https://github.com/stefanko-ch/Nexus-Stack/commit/1612409fd035e84ced9a4c92f892a551dff8e1a2))


### 🐛 Bug Fixes

* Address PR review comments from Copilot ([18274c7](https://github.com/stefanko-ch/Nexus-Stack/commit/18274c7cb29ca1cf327f557abead059939742f9e))
* Address second round of PR review comments ([98cdfc4](https://github.com/stefanko-ch/Nexus-Stack/commit/98cdfc4830b44b56ad4cd4851c0841b82915ead6))
* **ci:** Improve Hetzner S3 bucket cleanup in destroy-all workflow ([dd37e47](https://github.com/stefanko-ch/Nexus-Stack/commit/dd37e477df0c67b6dc762e22eb5af2884e4ba9de))
* **ci:** Remove stale .r2-credentials before recreating R2 token ([dded011](https://github.com/stefanko-ch/Nexus-Stack/commit/dded0111c656ae3cc4edd932c1fbbad227838b64))
* **ci:** Remove unused BUCKET_NAME variable in R2 validation ([cf01353](https://github.com/stefanko-ch/Nexus-Stack/commit/cf013538d9549e93825c03d8d1b7bad0b1ce80aa))
* **ci:** Validate numeric IDs in Close SSH port step ([858299f](https://github.com/stefanko-ch/Nexus-Stack/commit/858299f352f178dd1c042e200cb4e2e6833585fc))
* **ci:** Validate R2 credentials before use, auto-recreate if invalid ([efa8aa2](https://github.com/stefanko-ch/Nexus-Stack/commit/efa8aa207092db94f3099a01af62de67e1705bad))
* **scripts:** Use domain-based R2 API token naming for multi-user safety ([1df9350](https://github.com/stefanko-ch/Nexus-Stack/commit/1df9350fc535eb2a6410b58f7deac00d167fdc75))

## [0.20.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.19.1...v0.20.0) (2026-02-11)


### 🚀 Features

* **control-plane:** Add PUBLIC warning badge for public services ([6c04cb4](https://github.com/stefanko-ch/Nexus-Stack/commit/6c04cb40d1badde5a0941755b8afcd39e2345519))
* **stacks:** add Git proxy, auto-repo creation, and service Git bindings ([f0b08c4](https://github.com/stefanko-ch/Nexus-Stack/commit/f0b08c433841c8c7636f9c8a01bc836233647080))
* **stacks:** Add Gitea Git integration with proxy, user accounts, and service bindings ([945cb2d](https://github.com/stefanko-ch/Nexus-Stack/commit/945cb2d103a1b0f9c2083e7e41b198829c54648e))
* **stacks:** Add Gitea user account, private repo, and Infisical secrets ([19dd8cd](https://github.com/stefanko-ch/Nexus-Stack/commit/19dd8cda47998c33ba33d50d4e7be5cc499bb801))


### 🐛 Bug Fixes

* Address PR review - .netrc auth, idempotent .env, error logging ([0546d48](https://github.com/stefanko-ch/Nexus-Stack/commit/0546d48c66543dd85d0342fa6e8d28eae8ee301e))
* **ci:** fix heredoc indentation corrupting R2 credentials and config files ([1e1ec13](https://github.com/stefanko-ch/Nexus-Stack/commit/1e1ec1381f5647d2cdd11fda9a44bfe7eb0e27fd))
* **ci:** indent heredoc content and strip with sed to prevent YAML corruption ([7adbe0d](https://github.com/stefanko-ch/Nexus-Stack/commit/7adbe0d52e9953ec50cec8c1b30738483b7c2745))
* **ci:** remove empty expression placeholder from comment ([8a4ba09](https://github.com/stefanko-ch/Nexus-Stack/commit/8a4ba09b2263be924e967e612a080f489f8957a3))
* **ci:** remove SSH key masking that corrupts R2 credentials ([ad2287e](https://github.com/stefanko-ch/Nexus-Stack/commit/ad2287e309f432272f06e0270b7771fabb5404c4))
* **ci:** remove SSH key masking that corrupts R2 credentials ([f747141](https://github.com/stefanko-ch/Nexus-Stack/commit/f747141560aa40264154f47364c9924716b1f478))
* **ci:** restore SSH key heredoc indentation for YAML parser compatibility ([56f7125](https://github.com/stefanko-ch/Nexus-Stack/commit/56f71257ed50b239c59a53d4019fe21144dbe1c2))
* **ci:** use indented heredocs with sed strip for YAML parser compatibility ([97e99ef](https://github.com/stefanko-ch/Nexus-Stack/commit/97e99ef4608065aaa5abbb13868aa4c66d90c392))
* **scripts:** address PR review feedback for SSH error debugging ([9242be2](https://github.com/stefanko-ch/Nexus-Stack/commit/9242be282365a2c19a052efae98d64b96bde07a2))
* **scripts:** show SSH errors instead of suppressing with 2&gt;/dev/null ([570ca31](https://github.com/stefanko-ch/Nexus-Stack/commit/570ca3186c5df004291c1186edb5b3933439f202))
* **scripts:** show SSH errors instead of suppressing with 2&gt;/dev/null ([ef0342d](https://github.com/stefanko-ch/Nexus-Stack/commit/ef0342d38608caf3bd7610f4b843d5dcd389eefd))
* **scripts:** Use curl -s instead of curl -sf for Gitea API calls ([4466f43](https://github.com/stefanko-ch/Nexus-Stack/commit/4466f430a2382c132798e6990cea94cdea03aef8))
* **stacks:** Disable Marimo access token (behind Cloudflare Access) ([113802b](https://github.com/stefanko-ch/Nexus-Stack/commit/113802b63ad0119fc174c082030206b6f849ac51))
* **stacks:** Fix code-server 502 caused by escaped variable in command ([bdd7b40](https://github.com/stefanko-ch/Nexus-Stack/commit/bdd7b401e293ae444f7b6fb8907f7dc11eda061d))
* **stacks:** Use entrypoint instead of command for code-server ([c6ba2f2](https://github.com/stefanko-ch/Nexus-Stack/commit/c6ba2f27515668133e5354f47cf5709048a6bc51))
* **tofu:** Exclude public services from Cloudflare Access Application ([4fec1e4](https://github.com/stefanko-ch/Nexus-Stack/commit/4fec1e44e10eae446ec0f1a1454649fe2b0ec5b9))

## [0.19.1](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.19.0...v0.19.1) (2026-02-09)


### 🐛 Bug Fixes

* **ci:** mask SSH private key in logs and harden file creation ([0bad5a6](https://github.com/stefanko-ch/Nexus-Stack/commit/0bad5a61ef0fb7ef107e0f898a417ed6de2495e2))
* **ci:** pass SSH private key as workflow output for initial setup ([11c0421](https://github.com/stefanko-ch/Nexus-Stack/commit/11c0421eddb306f24336f0f3890d182b4656c390))
* **ci:** pass SSH private key as workflow output for initial setup ([9d0a1fb](https://github.com/stefanko-ch/Nexus-Stack/commit/9d0a1fbb8f1336ebaefde06259aec3d7e91c9ae2))
* **ci:** replace useless cat with input redirection (SC2002) ([320ed12](https://github.com/stefanko-ch/Nexus-Stack/commit/320ed12ae11e344db44bf0900291b73191ea3372))
* skip scheduled teardown when infrastructure is not deployed ([1f22c7e](https://github.com/stefanko-ch/Nexus-Stack/commit/1f22c7e769c65b154527901f61e84f8a0df081cf))
* **worker:** address PR review feedback for infra status check ([3e35544](https://github.com/stefanko-ch/Nexus-Stack/commit/3e35544cf1e83ee8c6c1c20827dd9fe67cc76324))
* **worker:** skip scheduled teardown when infrastructure is not deployed ([9fb9f7d](https://github.com/stefanko-ch/Nexus-Stack/commit/9fb9f7d1f3d8e905a031d7cb50c179eabce41831))

## [0.19.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.18.0...v0.19.0) (2026-02-08)


### 🚀 Features

* **stacks:** Add Trino distributed SQL query engine ([8f60a6a](https://github.com/stefanko-ch/Nexus-Stack/commit/8f60a6a65f4ea8da7bf66474a79f18da7361b9cb))
* **stacks:** Add Trino distributed SQL query engine ([ce07a3a](https://github.com/stefanko-ch/Nexus-Stack/commit/ce07a3a2ef7595370f0f277e5d0852f53dadc896)), closes [#91](https://github.com/stefanko-ch/Nexus-Stack/issues/91)


### 🐛 Bug Fixes

* **stacks:** address Trino PR review feedback ([fa7c62e](https://github.com/stefanko-ch/Nexus-Stack/commit/fa7c62eece841680e687de513e3476410c0e4e47))
* **stacks:** allow forwarded headers in Trino for Cloudflare Tunnel ([395abb5](https://github.com/stefanko-ch/Nexus-Stack/commit/395abb5786267347cbe07b465fca49f617e6bf55))

## [0.18.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.17.0...v0.18.0) (2026-02-08)


### 🚀 Features

* **stacks:** Add ClickHouse analytics database ([b54d0cc](https://github.com/stefanko-ch/Nexus-Stack/commit/b54d0cc6b007d4294f00d62b4b480f50f376506b))
* **stacks:** Add ClickHouse analytics database ([2b8aba4](https://github.com/stefanko-ch/Nexus-Stack/commit/2b8aba4d893df72967b682b4de5d9c87981284ae)), closes [#26](https://github.com/stefanko-ch/Nexus-Stack/issues/26)


### 🐛 Bug Fixes

* **control-plane:** use European date format in logs page ([af86261](https://github.com/stefanko-ch/Nexus-Stack/commit/af86261ef0119d61b77f059cc29852b56ae2df5a))
* **stacks:** correct ClickHouse image tag to 25.8.16.34 ([7ef9830](https://github.com/stefanko-ch/Nexus-Stack/commit/7ef983066abe747806ff2710c717b5d5f6c86751))

## [0.17.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.16.0...v0.17.0) (2026-02-07)


### 🚀 Features

* **stacks:** Add Gitea stack with persistent Hetzner Cloud Volume ([9fb139a](https://github.com/stefanko-ch/Nexus-Stack/commit/9fb139a0bed8388b14478971017221a73cf01fc7)), closes [#158](https://github.com/stefanko-ch/Nexus-Stack/issues/158)
* **stacks:** Add Gitea stack with persistent volume and fix scheduled teardown ([b1402c5](https://github.com/stefanko-ch/Nexus-Stack/commit/b1402c5097955fa21a872345f650d97b9e42fda0))


### 🐛 Bug Fixes

* **ci:** add missing newline before persistent_volume_id in destroy-all ([fca8958](https://github.com/stefanko-ch/Nexus-Stack/commit/fca8958d53d8bde537019b5613bf6d2f059925c3))
* **stacks:** add INSTALL_LOCK to Gitea to skip web installer ([4054f49](https://github.com/stefanko-ch/Nexus-Stack/commit/4054f490d7197eac2e9c9aa2f05a89bf925d7568))
* **tofu:** merge worker cron triggers into single resource ([20c37e0](https://github.com/stefanko-ch/Nexus-Stack/commit/20c37e037c5bd562cfea237d16a3341134a6f284))

## [0.16.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.15.0...v0.16.0) (2026-02-06)


### 🚀 Features

* **stacks:** Add OpenMetadata data catalog stack ([3946703](https://github.com/stefanko-ch/Nexus-Stack/commit/3946703df991264475deccc18b797a136b3db801))
* **stacks:** Add OpenMetadata data catalog stack ([ed1ff3c](https://github.com/stefanko-ch/Nexus-Stack/commit/ed1ff3c7215f751bd123c4dff6ea47113122e9ef)), closes [#84](https://github.com/stefanko-ch/Nexus-Stack/issues/84)


### 🐛 Bug Fixes

* **scripts:** Base64 encode passwords for OpenMetadata API ([4cd1185](https://github.com/stefanko-ch/Nexus-Stack/commit/4cd11855da08cc38afa6d278c9b1101c63429e84))
* **scripts:** Define OM_PRINCIPAL_DOMAIN unconditionally in deploy.sh ([2840d18](https://github.com/stefanko-ch/Nexus-Stack/commit/2840d186be204160ba96564fb2b140a89994a9fd))
* **scripts:** Remove duplicate OM_PRINCIPAL_DOMAIN definition ([9633a99](https://github.com/stefanko-ch/Nexus-Stack/commit/9633a99f80e749fa931cbfbf07caea35073ae2cf))
* **scripts:** Require special chars in OpenMetadata admin password ([6f31221](https://github.com/stefanko-ch/Nexus-Stack/commit/6f3122120ab78a856af0864fc66a6b629bb1a10a))
* **scripts:** Use correct OpenMetadata password change endpoint ([d9f9998](https://github.com/stefanko-ch/Nexus-Stack/commit/d9f99987c8830fe8ad9d4bd749c226ef7b03279d))
* **scripts:** Use plain text passwords for OpenMetadata password change API ([b858b96](https://github.com/stefanko-ch/Nexus-Stack/commit/b858b963ca2aa1619f6943b38eebc8ac58589b7e))
* **stacks:** Rename openmetadata-server container to openmetadata ([7604a6d](https://github.com/stefanko-ch/Nexus-Stack/commit/7604a6d8906fec20a71fea61b6caa916bd8d15b1))

## [0.15.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.14.0...v0.15.0) (2026-02-06)


### 🚀 Features

* **stacks:** Add Windmill workflow engine stack ([94fd687](https://github.com/stefanko-ch/Nexus-Stack/commit/94fd68733ddfc095501d328813c68362fc6b16b8))
* **stacks:** Add Windmill workflow engine stack ([5a941c2](https://github.com/stefanko-ch/Nexus-Stack/commit/5a941c226f5a90322bb90510b19948daf4deb895)), closes [#176](https://github.com/stefanko-ch/Nexus-Stack/issues/176)
* **windmill:** Auto-configure workspace and secure default credentials ([aeb4654](https://github.com/stefanko-ch/Nexus-Stack/commit/aeb4654668453ab263c4a55dfdf5b83a5ac19025))


### 🐛 Bug Fixes

* **ci:** Use dynamic worker name and remove unused wrangler.toml ([6d123fd](https://github.com/stefanko-ch/Nexus-Stack/commit/6d123fd73bb0d48fdd32cdd9b9575845cb896ea7))
* **windmill:** Auto-configure admin user with generated credentials ([d299d35](https://github.com/stefanko-ch/Nexus-Stack/commit/d299d3592202abebc7d4857e469a1b9d026c9df1))
* **windmill:** Create user account for $USER_EMAIL if configured ([d3bb755](https://github.com/stefanko-ch/Nexus-Stack/commit/d3bb7558156e66f6702e042533bd65ec9c28e622))

## [0.14.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.13.0...v0.14.0) (2026-02-04)


### 🚀 Features

* **stacks:** Add 5 object storage stacks (Filestash, Garage, LakeFS, RustFS, SeaweedFS) ([#184](https://github.com/stefanko-ch/Nexus-Stack/issues/184)) ([f1e07f1](https://github.com/stefanko-ch/Nexus-Stack/commit/f1e07f17081bc49d77e7fd6effeaeca6dad1e8b3))

## [0.13.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.12.0...v0.13.0) (2026-02-02)


### 🚀 Features

* **stacks:** Add Prefect workflow orchestration platform ([80b61bb](https://github.com/stefanko-ch/Nexus-Stack/commit/80b61bb537347f5e5e632584298eb03684339dea))
* **stacks:** Add Prefect workflow orchestration platform ([81fd467](https://github.com/stefanko-ch/Nexus-Stack/commit/81fd467de20c9c6a4869438a86e8b7a3acc0a166))


### 🐛 Bug Fixes

* **prefect:** Add PREFECT_API_URL to prefect-services container ([e99430d](https://github.com/stefanko-ch/Nexus-Stack/commit/e99430d0715401b0434e379fd3b441d5ec5108ba))
* **stacks:** Set PREFECT_UI_API_URL for Cloudflare Tunnel access ([7e86a04](https://github.com/stefanko-ch/Nexus-Stack/commit/7e86a042a2c1c4bbede0d828007c4e67011bea0c))

## [0.12.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.11.0...v0.12.0) (2026-02-02)


### 🚀 Features

* **stacks:** Add Jupyter and code-server stacks ([aebcc18](https://github.com/stefanko-ch/Nexus-Stack/commit/aebcc18d7f466a5cd99e8547d7063033fa54b462)), closes [#31](https://github.com/stefanko-ch/Nexus-Stack/issues/31) [#45](https://github.com/stefanko-ch/Nexus-Stack/issues/45)
* **stacks:** Add Jupyter and code-server with pre-configured auth ([034172d](https://github.com/stefanko-ch/Nexus-Stack/commit/034172d995288d22b666b37aa583e19c0c5bb14b))


### 🐛 Bug Fixes

* **stacks:** Disable auth for code-server and Jupyter, pin image versions ([de190b7](https://github.com/stefanko-ch/Nexus-Stack/commit/de190b70b2743b018a861228d2d46e3e2fe82e3f))
* **stacks:** Revert code-server to latest (tag :4 doesn't exist) ([7d0ab97](https://github.com/stefanko-ch/Nexus-Stack/commit/7d0ab97afd0f8a233f2851ed781ddd8338ad1911))

## [0.11.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.10.0...v0.11.0) (2026-02-01)


### ⚠ BREAKING CHANGES

* **firewall:** RedPanda now runs in production mode instead of dev-container mode

### 🚀 Features

* **firewall:** Add Firewall Management for external TCP access ([#174](https://github.com/stefanko-ch/Nexus-Stack/issues/174)) ([7ef4fbd](https://github.com/stefanko-ch/Nexus-Stack/commit/7ef4fbd09cb2cf035232d8fccb60cabd19671314))


### 🐛 Bug Fixes

* **deploy:** Follow-up security and error handling improvements ([#179](https://github.com/stefanko-ch/Nexus-Stack/issues/179)) ([59430fc](https://github.com/stefanko-ch/Nexus-Stack/commit/59430fc36e836fcfeedb3b4180df51441dd1f08e))

## [0.10.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.9.0...v0.10.0) (2026-01-28)


### 🚀 Features

* **stacks:** Add Meltano and database management stacks ([4fa3811](https://github.com/stefanko-ch/Nexus-Stack/commit/4fa38115d02a54ef55ade4a4e1d0b1c3a11c76f5))
* **stacks:** Add Meltano data integration platform ([7185216](https://github.com/stefanko-ch/Nexus-Stack/commit/71852167b9b4387727f55934b7555a4cca48ae31))
* **stacks:** Add PostgreSQL, pgAdmin, and Adminer database stacks ([ab1de2c](https://github.com/stefanko-ch/Nexus-Stack/commit/ab1de2cd7b71d25ac8acac7f40bd8bfc83628fa8))
* **stacks:** Add Soda Core data quality stack ([c67aaf5](https://github.com/stefanko-ch/Nexus-Stack/commit/c67aaf562bd40e84390336adf522a5eb0f877bc7))
* **stacks:** Add Soda Core data quality stack ([91ef3d2](https://github.com/stefanko-ch/Nexus-Stack/commit/91ef3d2d4a4f96ce7fe7c361fb7f273ac7b4ce89))


### 🐛 Bug Fixes

* **ci:** Allow internal-only services in generate-services-tfvars.py ([485320b](https://github.com/stefanko-ch/Nexus-Stack/commit/485320ba6a69d8b892eed3572c6bdb09af92b9f6))
* **ci:** Allow internal-only services without subdomain in validation ([c27bc72](https://github.com/stefanko-ch/Nexus-Stack/commit/c27bc728d31a4619f7c5004dad7423a41bcabf8e))
* **docs:** Change Soda badge logo from 'soda' to 'database' ([ecd25e1](https://github.com/stefanko-ch/Nexus-Stack/commit/ecd25e174b506f43732c52ad9021cb829d8cfe4a))
* **infisical:** Add POSTGRES_USERNAME to secrets ([d30b906](https://github.com/stefanko-ch/Nexus-Stack/commit/d30b906310ab6e2e658528a0634e31db06539bc0))
* **meltano:** Correct Docker image name from meltanolabs to meltano ([a2c3d45](https://github.com/stefanko-ch/Nexus-Stack/commit/a2c3d45a1dc7069a553af55596903d8fcb21ac22))
* **scripts:** Update PostgreSQL .env path to match renamed directory ([66a5a2c](https://github.com/stefanko-ch/Nexus-Stack/commit/66a5a2ce7d2c1b58c531429fe0ffa6b39db29d06))
* **soda:** Add ARM64 support with custom Dockerfile ([47ffe98](https://github.com/stefanko-ch/Nexus-Stack/commit/47ffe98a1395c5ad8ea069f3c79b5cc0b59eac7b))
* **stacks:** Add dedicated PostgreSQL database to Soda stack ([ba0197e](https://github.com/stefanko-ch/Nexus-Stack/commit/ba0197e9cdc0e89391921d226b7ccbcd55dbdb4f))
* **stacks:** Improve database stack UX and Info-Page ([8cda85f](https://github.com/stefanko-ch/Nexus-Stack/commit/8cda85fb698eb2a5a86a5fd52196930e9245bbd1))
* **stacks:** Improve Info-Page labels and healthcheck for internal services ([61204c5](https://github.com/stefanko-ch/Nexus-Stack/commit/61204c5605e23f825d3756829c43c9a6d0ad600e))
* **stacks:** Rename postgresql folder to postgres to match service name ([6cef2ba](https://github.com/stefanko-ch/Nexus-Stack/commit/6cef2ba150ea7b59317a71b85d11cefbc09f1636))


### ♻️ Refactoring

* **meltano:** Convert to CLI-only internal service ([323721b](https://github.com/stefanko-ch/Nexus-Stack/commit/323721bc4424109d026e59bf992dadf1ee07a6f7))


### 📚 Documentation

* **instructions:** Add requirement to provide testing instructions ([a639b62](https://github.com/stefanko-ch/Nexus-Stack/commit/a639b6291750bc2fd8ab1cf863a648f35ef10435))
* **meltano:** Clarify CLI access via Wetty and SSH ([a59663a](https://github.com/stefanko-ch/Nexus-Stack/commit/a59663a1806d8fa3bd2ca62dc039a264745ef0a7))
* Sort stacks alphabetically in README ([bdfeb26](https://github.com/stefanko-ch/Nexus-Stack/commit/bdfeb26f7ec15ba6198b4bec1e46ff2cb8b2a992))

## [0.9.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.8.0...v0.9.0) (2026-01-25)


### 🚀 Features

* **stacks:** Add Hoppscotch API testing platform ([f93b682](https://github.com/stefanko-ch/Nexus-Stack/commit/f93b682bbf4f34dced4a682bae081305d81a4e84))
* **stacks:** Add Hoppscotch, Kafka-UI, and SSH/debugging docs ([3a9a4dc](https://github.com/stefanko-ch/Nexus-Stack/commit/3a9a4dcc943ff7c7d68d1fa6920281bfa3864202))
* **stacks:** Add Kafka-UI web interface for Redpanda ([af84d60](https://github.com/stefanko-ch/Nexus-Stack/commit/af84d6009edabafe0e23c91e0450f6d9f552ed84))
* **stacks:** Add Redpanda Connect and Datagen stacks ([ba8e912](https://github.com/stefanko-ch/Nexus-Stack/commit/ba8e912c30c296112cc60e14836c46873090d3e1)), closes [#125](https://github.com/stefanko-ch/Nexus-Stack/issues/125) [#140](https://github.com/stefanko-ch/Nexus-Stack/issues/140)


### 🐛 Bug Fixes

* **hoppscotch:** Update port mapping for new AIO image architecture ([4fa161a](https://github.com/stefanko-ch/Nexus-Stack/commit/4fa161a083de9a445aaf01c6a549576b476affaf))
* **hoppscotch:** Use exec to prevent container shutdown ([1c02aea](https://github.com/stefanko-ch/Nexus-Stack/commit/1c02aeac2528bc68896460e7defbca0669d7b4cf))
* **info-page:** Mark redpanda-connect and redpanda-datagen as non-clickable ([ba34976](https://github.com/stefanko-ch/Nexus-Stack/commit/ba349763f2c9d5031c300b1129b71b231c9d07e5))
* **stacks:** Add database migration step for Hoppscotch ([d26ab37](https://github.com/stefanko-ch/Nexus-Stack/commit/d26ab372842f196f3e22546fa832fad3d4a2b58b))
* **stacks:** Correct subdomain names for Redpanda Connect and Datagen ([32c75f7](https://github.com/stefanko-ch/Nexus-Stack/commit/32c75f7a558f57ae330dd7d91d27702f89d82d5a))
* **stacks:** Fix Bloblang mapping in redpanda-datagen ([0a8de7a](https://github.com/stefanko-ch/Nexus-Stack/commit/0a8de7a209a3f5b5caea11c39f9b4ac6f9f43936))
* **stacks:** Fix config path for Redpanda Connect containers ([d3e95c9](https://github.com/stefanko-ch/Nexus-Stack/commit/d3e95c91fa2eba76a722d1f2e5237c957c432ee6))
* **stacks:** Fix migration paths for Hoppscotch ([349bceb](https://github.com/stefanko-ch/Nexus-Stack/commit/349bceb41741b58498856a011de33bf13edd320f))
* **stacks:** Remove manual migration step for Hoppscotch ([82077d7](https://github.com/stefanko-ch/Nexus-Stack/commit/82077d7cd0efcc8515550968892de9f54cac96ba))
* **stacks:** Use correct Prisma migration command for Hoppscotch ([5e0a9e4](https://github.com/stefanko-ch/Nexus-Stack/commit/5e0a9e4b614d77ae0c3bcdef58e526b2d38f6ea9))
* **worker:** Add D1 logging for GitHub API errors ([a7f55a7](https://github.com/stefanko-ch/Nexus-Stack/commit/a7f55a71c0a54ddab00ee4f47d54f811adda080d))


### 📚 Documentation

* Add comprehensive debugging guide ([6c6db17](https://github.com/stefanko-ch/Nexus-Stack/commit/6c6db17f2902bb73f69fd57e0a8e0eb8a5f9b634))
* Add comprehensive SSH access guide ([e78a7af](https://github.com/stefanko-ch/Nexus-Stack/commit/e78a7af12228a03f34085e84e1545cf036f63809))
* Add no-advertising policy to agent instructions ([de6048c](https://github.com/stefanko-ch/Nexus-Stack/commit/de6048cff5c74ca843722b36ab067c0e8a4b373d))
* Fix badge order and improve stack addition guidelines ([7e87025](https://github.com/stefanko-ch/Nexus-Stack/commit/7e87025774e62d47a8385673f48bfaa7248b76b3))

## [0.8.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.7.0...v0.8.0) (2026-01-22)


### 🚀 Features

* **control-plane:** Add configurable policy to prevent auto-shutdown disable ([3ee0b4c](https://github.com/stefanko-ch/Nexus-Stack/commit/3ee0b4ccd33ee4cf4845cd0e62e03a9298d8a441))
* **docs:** Migrate agent instructions to CLAUDE.md and fix Mailpit UI ([e15655b](https://github.com/stefanko-ch/Nexus-Stack/commit/e15655b5fee300dc5759057a149a574ba4fa485a))
* **initial-setup:** Add enabled_services parameter for pre-selecting services ([e24e974](https://github.com/stefanko-ch/Nexus-Stack/commit/e24e974dfed3f6ff516caa0cdfea82c71d8a7250))
* **stacks:** Add Draw.io and fix D1 sync rate limits ([1e0ccd7](https://github.com/stefanko-ch/Nexus-Stack/commit/1e0ccd7dd0dd3364f1338d6171dc5e758e524046))
* **stacks:** Add Draw.io diagramming tool ([4bcecc6](https://github.com/stefanko-ch/Nexus-Stack/commit/4bcecc6b3a21ce45a577af01aed3d5c66b6f5bbc))
* **stack:** Service fixes, auto-shutdown policy, and documentation updates ([a089656](https://github.com/stefanko-ch/Nexus-Stack/commit/a089656f78e1b289779d6fb9377770a86ce76e6e))


### 🐛 Bug Fixes

* Address Copilot code review feedback ([af56167](https://github.com/stefanko-ch/Nexus-Stack/commit/af56167d1bcd362d93b22af9b95b5207b6274f29))
* Address PR review comments ([40eca99](https://github.com/stefanko-ch/Nexus-Stack/commit/40eca998b86f287fdbfc6f21f9665d2fd3aa8408))
* **ci:** Improve R2 credentials error handling ([918759c](https://github.com/stefanko-ch/Nexus-Stack/commit/918759c7a724ae79f801dda67cbbea8d1600c336))
* **ci:** Improve R2 credentials error messages in spin-up ([5bb0518](https://github.com/stefanko-ch/Nexus-Stack/commit/5bb0518498ac5fa59eb7f13d79682c1bd8133e72))
* **ci:** Use batch SQL execution to avoid D1 rate limits ([577e2d6](https://github.com/stefanko-ch/Nexus-Stack/commit/577e2d6f2abf654bfe32d61957728c03f9699c5f))
* **deploy:** Fix Metabase port configuration ([fe5b2d8](https://github.com/stefanko-ch/Nexus-Stack/commit/fe5b2d8723e85490d50645e6da4e51c4738bb794))
* **deploy:** Fix Wetty SSH key path variable escaping ([d4a5aea](https://github.com/stefanko-ch/Nexus-Stack/commit/d4a5aeae0ba660729d74e4086128a9d5c9536ae9))
* **docs:** Add Resend and Docker Hub to Quick Start Flow diagram ([48480f4](https://github.com/stefanko-ch/Nexus-Stack/commit/48480f468adbd0582ddd8b74456a8240a64ffac4))
* **info-page:** Change title from Dashboard to Info Dashboard ([ca605c9](https://github.com/stefanko-ch/Nexus-Stack/commit/ca605c96fa68dcd5bf1d9f1c0bcee9ac3155b121))
* **info-page:** Skip nested support_images blocks correctly ([9b970f1](https://github.com/stefanko-ch/Nexus-Stack/commit/9b970f11159c826cd0cca85e28d177bf9f7386cc))
* **scripts:** Add missing DIM color variable definition ([ec17f14](https://github.com/stefanko-ch/Nexus-Stack/commit/ec17f14b19e1c0700f6b9dd0d060753cec107582))
* **scripts:** Use dev environment for Infisical secrets ([9becc99](https://github.com/stefanko-ch/Nexus-Stack/commit/9becc99b405b51e15ca62023768517f2963395e3))
* **services:** Remove core flag from mailpit ([dc7a0e4](https://github.com/stefanko-ch/Nexus-Stack/commit/dc7a0e497d9c2907db609b6afd9bed9be5fa2ffa))
* **stacks:** Fix Mailpit and Kestra configuration issues ([2b28ea1](https://github.com/stefanko-ch/Nexus-Stack/commit/2b28ea16addc89f6b3b3648bee1614798152b475))


### 📚 Documentation

* Add 'How It Works' section with Medium article reference ([99228a1](https://github.com/stefanko-ch/Nexus-Stack/commit/99228a17adbe7fffcb5ae28a55d2a1adf9005c99))
* Add documentation for auto-shutdown policy configuration ([f8f6b45](https://github.com/stefanko-ch/Nexus-Stack/commit/f8f6b4563d5711590bbd9111724a06347b260f87))
* Add Mermaid diagrams for setup flow, architecture and security ([a4396b7](https://github.com/stefanko-ch/Nexus-Stack/commit/a4396b7c81780fbd1011493ddb85ca00dd3589bd))
* Add Nexus-Stack story article to README ([0989e94](https://github.com/stefanko-ch/Nexus-Stack/commit/0989e94235671a8e78ac6670e4932c013ccc6c76))
* Add Nexus-Stack story article to README ([02fc35f](https://github.com/stefanko-ch/Nexus-Stack/commit/02fc35f7d09a92782e7b9fa050173e06734f0aae))
* Add project website link to README ([6a61ca6](https://github.com/stefanko-ch/Nexus-Stack/commit/6a61ca6f78e1bda0577440da077bbd29b7aa7bc6))


### 🔧 Maintenance

* Clean up deployment documentation and update services ([8f6d2b2](https://github.com/stefanko-ch/Nexus-Stack/commit/8f6d2b2b53b83634357a758ee1fe3fd72f4594b1))
* Remove .cursor folder and add to gitignore ([3c76b3a](https://github.com/stefanko-ch/Nexus-Stack/commit/3c76b3a18a577859879b7e74b71564f79107c5fa))
* Remove local deployment references from code ([994de6b](https://github.com/stefanko-ch/Nexus-Stack/commit/994de6b09932b6729919d40ff79d33d29225970c))
* Remove Makefile and add Control Plane Guide to docs ([a992531](https://github.com/stefanko-ch/Nexus-Stack/commit/a99253132b3c4f3a3c14ff2b567871e6bb28faa7))

## [0.7.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.6.0...v0.7.0) (2026-01-20)


### ⚠ BREAKING CHANGES

* Local deployment (make up) is no longer supported. Use GitHub Actions workflows exclusively.

### 🚀 Features

* **control-plane:** Add service toggles with D1 as single source of truth ([eb70181](https://github.com/stefanko-ch/Nexus-Stack/commit/eb70181f1f7c7df6241fff299454635d4e4edb38))
* **control-plane:** Add Show Info button to header navigation ([2fdb4ca](https://github.com/stefanko-ch/Nexus-Stack/commit/2fdb4cae589b3e2896adf0681de2786a0e8c5109))
* **control-plane:** Add staged service toggles with pending changes UI ([a59312f](https://github.com/stefanko-ch/Nexus-Stack/commit/a59312f4aa185159b12ba4750ecfe3edbc603703))
* **stacks:** Add Wetty stack and improve service sync debugging ([ffd2848](https://github.com/stefanko-ch/Nexus-Stack/commit/ffd28485fd857ccc29b591c498b2325d88d4819c))
* **stacks:** Add Wetty web-based SSH terminal ([ab7293c](https://github.com/stefanko-ch/Nexus-Stack/commit/ab7293cdcf47e5c1d8721346bf154e00c230a21e)), closes [#139](https://github.com/stefanko-ch/Nexus-Stack/issues/139)
* **wetty:** Enable Wetty by default ([d6d71da](https://github.com/stefanko-ch/Nexus-Stack/commit/d6d71da890a3e2d87fb6ac8a32157262799c1050))
* **wetty:** Make Wetty a core service with enhanced security ([ed12a86](https://github.com/stefanko-ch/Nexus-Stack/commit/ed12a868fb1066819afc5caae4cc6d1ad0678c0f))


### 🐛 Bug Fixes

* Address Copilot review comments ([1dd1e2a](https://github.com/stefanko-ch/Nexus-Stack/commit/1dd1e2a27a09d4f93ea1d704873c6eceb10f5860))
* Address remaining PR review comments ([de863c0](https://github.com/stefanko-ch/Nexus-Stack/commit/de863c0196435aca451702fcf30d860dabb78aea))
* Address remaining PR review comments ([44b8303](https://github.com/stefanko-ch/Nexus-Stack/commit/44b830300e77ba8af6a53dd4dcb53d2882ac1df2))
* **ci:** Add missing generate-services-tfvars.py script ([7748f8b](https://github.com/stefanko-ch/Nexus-Stack/commit/7748f8ba7a8229011c1fb5bead3eb8e1b644969c))
* **ci:** Add R2 bucket cleanup to destroy workflow ([ce3cc9b](https://github.com/stefanko-ch/Nexus-Stack/commit/ce3cc9b66a50daf85212a2d5d8dc58d52c5a79c2))
* **ci:** Core services always enabled regardless of D1 state ([b359223](https://github.com/stefanko-ch/Nexus-Stack/commit/b359223a5e4140fa7c797344351229f3d9b10cb4))
* **ci:** Fix missing newline causing last service (Wetty) to be skipped ([30715fe](https://github.com/stefanko-ch/Nexus-Stack/commit/30715fee1e9ce93150f71a868725c5434d5a9250))
* **ci:** Fix missing newline causing last service (Wetty) to be skipped ([503237e](https://github.com/stefanko-ch/Nexus-Stack/commit/503237ea0b76393b7dd3e4ebea1645f244dc08ca))
* **ci:** Fix regex parsing for services.tfvars ([90ec676](https://github.com/stefanko-ch/Nexus-Stack/commit/90ec676e34494f79a22f6f050b9a528038a999bc))
* **ci:** Improve sync-deployed-state.sh with detailed logging and error handling ([a565c1f](https://github.com/stefanko-ch/Nexus-Stack/commit/a565c1f13155662063fb2dc31e53c8f1902e063c))
* **ci:** Make D1 single source of truth for all workflows ([26fd3ec](https://github.com/stefanko-ch/Nexus-Stack/commit/26fd3ec46e84f49bd603aed9cacd91037bdddc90))
* **ci:** Revert to wrangler for D1 sync (API behind Cloudflare Access) ([9991d63](https://github.com/stefanko-ch/Nexus-Stack/commit/9991d631867a9afb481db1a1c2fdff71be68c3c3))
* **control-plane:** Enable Spin Up button for pending service changes ([dcecc8d](https://github.com/stefanko-ch/Nexus-Stack/commit/dcecc8d50e20145e45eefccb8fe35d3f73bec82d))
* **control-plane:** Fix Control Plane and Info Page issues ([deecb26](https://github.com/stefanko-ch/Nexus-Stack/commit/deecb266942d898aec94d99e032c5c013a0698f5))
* **control-plane:** Fix multiple Control Plane and Info Page issues ([ecd4094](https://github.com/stefanko-ch/Nexus-Stack/commit/ecd409472ba777f334eeba91865e738941ec8a52))
* **pr:** Address PR review comments ([cd6bd50](https://github.com/stefanko-ch/Nexus-Stack/commit/cd6bd504a1909b446325c597b709cef2eefab2ff))
* Resolve authentication issues and improve Control Plane UX ([e5b6930](https://github.com/stefanko-ch/Nexus-Stack/commit/e5b6930d5776e3d20632120e66d01aeacc178e38))
* Resolve authentication issues for Kestra, n8n, and Wetty ([1dba685](https://github.com/stefanko-ch/Nexus-Stack/commit/1dba6856e151208c93c5db7c883c7540fd1a402c))
* **scripts:** Fix service parsing to skip outer wrapper and nested blocks ([c759b24](https://github.com/stefanko-ch/Nexus-Stack/commit/c759b24fe85b8a8c31e023bc39fac4369592103f))
* **scripts:** Generate SSH key pair for Wetty on server ([85122f7](https://github.com/stefanko-ch/Nexus-Stack/commit/85122f7e10eb78e40271aef65e467ef338e8ceb2))
* **scripts:** Improve sync-deployed-state script with better logging and error handling ([7ec0b79](https://github.com/stefanko-ch/Nexus-Stack/commit/7ec0b79d2fc05beaecfb4c77fa304c9bf7d0eda8))
* **scripts:** Initialize CONFIG_JOBS array to prevent unbound variable error ([48c0815](https://github.com/stefanko-ch/Nexus-Stack/commit/48c0815a319341a4c45573488ea8075dde6b2283))
* **stacks:** Use command flags instead of env vars for wetty configuration ([b656599](https://github.com/stefanko-ch/Nexus-Stack/commit/b65659900bc97480b0ff8e9c69d6ff6bf23033de))
* **tunnel:** Stop existing tunnel service before installing new token ([093ccba](https://github.com/stefanko-ch/Nexus-Stack/commit/093ccba373782587a35debec042315b01679f4eb))
* **ui:** Improve domain extraction for multi-part TLDs ([17c14e8](https://github.com/stefanko-ch/Nexus-Stack/commit/17c14e885ac65575f88b4dec69bb2450636c8e61))
* **wetty:** Fix SSH_AUTH_SOCK path in container ([2be0b8c](https://github.com/stefanko-ch/Nexus-Stack/commit/2be0b8c90944c88d323377b46c581d238d18bafe))
* **worker:** Make cron schedules configurable via environment variables ([17c14e8](https://github.com/stefanko-ch/Nexus-Stack/commit/17c14e885ac65575f88b4dec69bb2450636c8e61))
* **worker:** Replace time comparison with cron-based action selection ([99715c7](https://github.com/stefanko-ch/Nexus-Stack/commit/99715c764959198d0f3cf06420073ec2bdd4cb3f))


### ♻️ Refactoring

* **config:** migrate services.tfvars to services.yaml ([f92b62a](https://github.com/stefanko-ch/Nexus-Stack/commit/f92b62a5d97718446b1918d3f5b3ce738bc05baf))
* **control-plane:** Make D1 single source of truth for services ([e321e59](https://github.com/stefanko-ch/Nexus-Stack/commit/e321e593f33209ee832cd4e2ac6ec554cbf76f4e))
* Remove local deployment support, consolidate image versions ([08460cd](https://github.com/stefanko-ch/Nexus-Stack/commit/08460cd7f479befd41035f9cb92d95bf302b8797))
* **sync-deployed-state:** Enhance service synchronization logic ([c84f266](https://github.com/stefanko-ch/Nexus-Stack/commit/c84f266d10cda9eead536d82dea94e6480d30fd5))
* **wetty:** Make Wetty optional instead of core service ([9f78b70](https://github.com/stefanko-ch/Nexus-Stack/commit/9f78b70d07d73fa84f041a88afb6d6e3c3330008))


### 📚 Documentation

* Add commit and push workflow instructions for agents ([d970d2c](https://github.com/stefanko-ch/Nexus-Stack/commit/d970d2c00b9e4a9377e4315887d92b3f25fccb24))
* **agents:** Add instruction to check for related issues when creating PRs ([092b152](https://github.com/stefanko-ch/Nexus-Stack/commit/092b15265a7e5d9aa3734fb026f1c91e50894d2e))
* Update Wetty documentation for 1h session duration ([4297811](https://github.com/stefanko-ch/Nexus-Stack/commit/429781154f51c7c35fd42220abb0a21a8750caf9))


### 🔧 Maintenance

* Remove unused API endpoints (wrangler handles D1 sync) ([22436b4](https://github.com/stefanko-ch/Nexus-Stack/commit/22436b4e404177cd511bc37926f6baa0e4369d7c))

## [0.6.0](https://github.com/stefanko-ch/Nexus-Stack/compare/v0.5.0...v0.6.0) (2026-01-19)


### 🚀 Features

* **control-plane:** migrate from KV to D1 database ([#146](https://github.com/stefanko-ch/Nexus-Stack/issues/146)) ([fb665c3](https://github.com/stefanko-ch/Nexus-Stack/commit/fb665c3c1091aec15ec2b968dcb25c5d322eacf7))

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
