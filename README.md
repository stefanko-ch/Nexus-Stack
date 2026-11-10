# Nexus-Stack

![Nexus-Stack](docs/assets/Nexus-Logo-BlackWhite.png)

[![GitHub License](https://img.shields.io/github/license/stefanko-ch/Nexus-Stack)](https://github.com/stefanko-ch/Nexus-Stack/blob/main/LICENSE)
[![Tests](https://github.com/stefanko-ch/Nexus-Stack/actions/workflows/python-tests.yml/badge.svg)](https://github.com/stefanko-ch/Nexus-Stack/actions/workflows/python-tests.yml)
[![GitHub Release](https://img.shields.io/github/v/release/stefanko-ch/Nexus-Stack)](https://github.com/stefanko-ch/Nexus-Stack/releases)
[![Docs](https://img.shields.io/badge/docs-nexus--stack.ch-0b6e5f)](https://nexus-stack.ch/docs/)

**A self-hosted data platform on one server that you can switch off at night.**

Pick the tools you need, click Spin Up, and work in the browser. The server has
no open ports, and there is nothing to install on your own machine.

## What you get

- **A catalogue of data tools.** Databases, streaming, orchestration, notebooks,
  BI and AI tooling, each one a switch in a web page.
- **A server that only exists while you use it.** Teardown destroys the machine
  and keeps your data. Spin Up builds a new one and puts the data back. An
  optional daily schedule runs the teardown for you.
- **No open ports.** Web interfaces are reached through Cloudflare Tunnel, and
  Cloudflare Access asks for an email login first. The one exception is Git
  Proxy, which is public by design. Internal-only stacks such as Postgres have
  no route from outside at all. The server accepts no inbound connections
  unless you open a port yourself on the Firewall page.
- **Nothing to run locally.** Every change is a GitHub Actions workflow.
  Passwords are generated for you and stored in Infisical.

New here? [What is Nexus Stack?](docs/concepts/index.md) explains the problem it
solves and what it deliberately is not.

## How it works

The Control Plane is a web page that stores what you want: which stacks are on,
your settings, your firewall rules. GitHub Actions turns that into a Hetzner
Cloud server with OpenTofu and starts your stacks on it with Docker. You reach
their web interfaces through Cloudflare, which asks for an email login unless
a stack is marked public.

- [Architecture](docs/concepts/architecture.md): the three planes and where state lives
- [Lifecycle](docs/concepts/lifecycle.md): what survives a teardown, and the two lifecycle modes
- [Security model](docs/concepts/security-model.md): why no port is open, and what the Firewall page changes

## Stacks (163)

[![Adminer](https://img.shields.io/badge/Adminer-34567C?logo=adminer&logoColor=white)](https://www.adminer.org)
[![Airflow](https://img.shields.io/badge/Apache_Airflow-017CEE?logo=apacheairflow&logoColor=white)](https://airflow.apache.org)
[![AKHQ](https://img.shields.io/badge/AKHQ-000000?logo=apachekafka&logoColor=white)](https://akhq.io)
[![AnythingLLM](https://img.shields.io/badge/AnythingLLM-0E0F0F?logoColor=white)](https://anythingllm.com)
[![Apache Fluss](https://img.shields.io/badge/Apache_Fluss-1E40AF?logo=apache&logoColor=white)](https://fluss.apache.org)
[![Apache Hop](https://img.shields.io/badge/Apache_Hop-3A6EA5?logo=apache&logoColor=white)](https://hop.apache.org)
[![Apache Kafka](https://img.shields.io/badge/Apache_Kafka-231F20?logo=apachekafka&logoColor=white)](https://kafka.apache.org)
[![Apache NiFi](https://img.shields.io/badge/Apache_NiFi-728E9B?logo=apachenifi&logoColor=white)](https://nifi.apache.org)
[![Apicurio](https://img.shields.io/badge/Apicurio-CE1126?logoColor=white)](https://www.apicur.io/registry/)
[![Appsmith](https://img.shields.io/badge/Appsmith-F86A2E?logo=appsmith&logoColor=white)](https://appsmith.com)
[![ArcadeDB](https://img.shields.io/badge/ArcadeDB-2E7D32?logoColor=white)](https://arcadedb.com)
[![Arize Phoenix](https://img.shields.io/badge/Arize_Phoenix-F56565?logoColor=white)](https://phoenix.arize.com)
[![Baserow](https://img.shields.io/badge/Baserow-5190EF?logo=baserow&logoColor=white)](https://baserow.io)
[![Big-AGI](https://img.shields.io/badge/Big--AGI-FF6B35?logo=openai&logoColor=white)](https://github.com/enricoros/big-agi)
[![BookStack](https://img.shields.io/badge/BookStack-0288D1?logo=bookstack&logoColor=white)](https://www.bookstackapp.com)
[![Budibase](https://img.shields.io/badge/Budibase-9981F5?logo=budibase&logoColor=white)](https://budibase.com)
[![Bytebase](https://img.shields.io/badge/Bytebase-5B4FE9?logoColor=white)](https://www.bytebase.com)
[![Cassandra](https://img.shields.io/badge/Apache_Cassandra-1287B1?logo=apachecassandra&logoColor=white)](https://cassandra.apache.org)
[![Chroma](https://img.shields.io/badge/Chroma-F87171?logo=databricks&logoColor=white)](https://www.trychroma.com)
[![ClickHouse](https://img.shields.io/badge/ClickHouse-FFCC00?logo=clickhouse&logoColor=black)](https://clickhouse.com)
[![CloudBeaver](https://img.shields.io/badge/CloudBeaver-3776AB?logo=dbeaver&logoColor=white)](https://dbeaver.com/cloudbeaver/)
[![code-server](https://img.shields.io/badge/code--server-007ACC?logo=visualstudiocode&logoColor=white)](https://coder.com)
[![Conduit](https://img.shields.io/badge/Conduit-00A3E0?logoColor=white)](https://conduit.io)
[![Crawl4AI](https://img.shields.io/badge/Crawl4AI-1B6CA8?logo=googlechrome&logoColor=white)](https://github.com/unclecode/crawl4ai)
[![Cube](https://img.shields.io/badge/Cube-FF6492?logoColor=white)](https://cube.dev)
[![CyberChef](https://img.shields.io/badge/CyberChef-1B365D?logo=gchq&logoColor=white)](https://gchq.github.io/CyberChef/)
[![Dagster](https://img.shields.io/badge/Dagster-4F43DD?logo=dagster&logoColor=white)](https://dagster.io)
[![Data Contract API](https://img.shields.io/badge/Data_Contract_API-0F766E?logoColor=white)](https://cli.datacontract.com)
[![Data Contract Editor](https://img.shields.io/badge/Data_Contract_Editor-1E293B?logoColor=white)](https://github.com/datacontract/datacontract-editor)
[![DataOps TestGen](https://img.shields.io/badge/DataOps_TestGen-06B6D4?logoColor=white)](https://datakitchen.io/dataops-testgen/)
[![Datasette](https://img.shields.io/badge/Datasette-0F3E66?logoColor=white)](https://datasette.io)
[![Debezium](https://img.shields.io/badge/Debezium-4E8CBF?logo=debezium&logoColor=white)](https://debezium.io)
[![Dify](https://img.shields.io/badge/Dify-1677FF?logoColor=white)](https://dify.ai)
[![Dinky](https://img.shields.io/badge/Dinky-1677FF?logo=apacheflink&logoColor=white)](https://www.dinky.org.cn/)
[![Directus](https://img.shields.io/badge/Directus-6644FF?logo=directus&logoColor=white)](https://directus.io)
[![Docling](https://img.shields.io/badge/Docling-0F62FE?logoColor=white)](https://docling-project.github.io/docling/)
[![Dozzle](https://img.shields.io/badge/Dozzle-7B16FF?logo=docker&logoColor=white)](https://dozzle.dev)
[![DragonflyDB](https://img.shields.io/badge/DragonflyDB-0D1117?logo=redis&logoColor=white)](https://www.dragonflydb.io)
[![Draw.io](https://img.shields.io/badge/Draw.io-F08705?logo=diagramsdotnet&logoColor=white)](https://www.diagrams.net)
[![Dremio](https://img.shields.io/badge/Dremio-31B48D?logoColor=white)](https://www.dremio.com)
[![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?logo=duckdb&logoColor=black)](https://duckdb.org)
[![Entropy Data](https://img.shields.io/badge/Entropy_Data-111827?logoColor=white)](https://www.entropy-data.com)
[![Evidence](https://img.shields.io/badge/Evidence-7B61FF?logo=markdown&logoColor=white)](https://evidence.dev)
[![Evidently](https://img.shields.io/badge/Evidently-ED0400?logoColor=white)](https://www.evidentlyai.com)
[![Excalidraw](https://img.shields.io/badge/Excalidraw-6965DB?logo=excalidraw&logoColor=white)](https://excalidraw.com)
[![Filestash](https://img.shields.io/badge/Filestash-2B3A67?logo=files&logoColor=white)](https://www.filestash.app)
[![Flink](https://img.shields.io/badge/Apache_Flink-E6526F?logo=apacheflink&logoColor=white)](https://flink.apache.org)
[![Flowise](https://img.shields.io/badge/Flowise-4F46E5?logo=langchain&logoColor=white)](https://flowiseai.com)
[![Forgejo](https://img.shields.io/badge/Forgejo-FB923C?logo=forgejo&logoColor=white)](https://forgejo.org)
[![Forgejo Runner](https://img.shields.io/badge/Forgejo_Runner-FB923C?logo=forgejo&logoColor=white)](docs/stacks/forgejo-runner.md)
[![Garage](https://img.shields.io/badge/Garage-59C6A6?logo=amazons3&logoColor=white)](https://garagehq.deuxfleurs.fr)
[![Git Proxy](https://img.shields.io/badge/Git_Proxy-009639?logo=nginx&logoColor=white)](docs/stacks/git-proxy.md)
[![Gitea](https://img.shields.io/badge/Gitea-609926?logo=gitea&logoColor=white)](https://about.gitea.com)
[![GPT Researcher](https://img.shields.io/badge/GPT_Researcher-111827?logoColor=white)](https://gptr.dev)
[![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)](https://grafana.com)
[![Grafana Tempo](https://img.shields.io/badge/Grafana_Tempo-F46800?logo=grafana&logoColor=white)](https://grafana.com/oss/tempo/)
[![Gravitino](https://img.shields.io/badge/Apache_Gravitino-2B6CB0?logo=apache&logoColor=white)](https://gravitino.apache.org)
[![Grist](https://img.shields.io/badge/Grist-16B378?logoColor=white)](https://www.getgrist.com)
[![Hasura](https://img.shields.io/badge/Hasura-1EB4D4?logo=hasura&logoColor=white)](https://hasura.io)
[![HedgeDoc](https://img.shields.io/badge/HedgeDoc-3499D9?logo=hedgedoc&logoColor=white)](https://hedgedoc.org)
[![Hive Metastore](https://img.shields.io/badge/Apache_Hive-FDEE21?logo=apachehive&logoColor=black)](https://hive.apache.org)
[![Hoppscotch](https://img.shields.io/badge/Hoppscotch-201718?logo=hoppscotch&logoColor=white)](https://hoppscotch.io)
[![Hue](https://img.shields.io/badge/Hue-4A90E2?logo=apachehadoop&logoColor=white)](https://gethue.com)
[![Infisical](https://img.shields.io/badge/Infisical-000000?logo=infisical&logoColor=white)](https://infisical.com)
[![InfluxDB](https://img.shields.io/badge/InfluxDB-22ADF6?logo=influxdb&logoColor=white)](https://www.influxdata.com/products/influxdb/)
[![IT-Tools](https://img.shields.io/badge/IT--Tools-5D5D5D?logo=homeassistant&logoColor=white)](https://it-tools.tech)
[![Jena Fuseki](https://img.shields.io/badge/Apache_Jena_Fuseki-D22128?logo=apache&logoColor=white)](https://jena.apache.org/documentation/fuseki2/)
[![Jupyter](https://img.shields.io/badge/Jupyter-F37726?logo=jupyter&logoColor=white)](https://jupyter.org)
[![Kafdrop](https://img.shields.io/badge/Kafdrop-000000?logo=apachekafka&logoColor=white)](https://github.com/obsidiandynamics/kafdrop)
[![Kafka-UI](https://img.shields.io/badge/Kafka--UI-000000?logo=apachekafka&logoColor=white)](https://docs.kafka-ui.provectus.io/)
[![Kestra](https://img.shields.io/badge/Kestra-6047EC?logo=kestra&logoColor=white)](https://kestra.io)
[![Keycloak](https://img.shields.io/badge/Keycloak-4D4D4D?logo=keycloak&logoColor=white)](https://www.keycloak.org)
[![ksqlDB](https://img.shields.io/badge/ksqlDB-231F20?logo=apachekafka&logoColor=white)](https://ksqldb.io)
[![Label Studio](https://img.shields.io/badge/Label_Studio-FF7557?logo=labelstudio&logoColor=white)](https://labelstud.io)
[![LakeFS](https://img.shields.io/badge/LakeFS-00B4D8?logo=git&logoColor=white)](https://lakefs.io)
[![Lakekeeper](https://img.shields.io/badge/Lakekeeper-B7410E?logo=rust&logoColor=white)](https://lakekeeper.io)
[![Langflow](https://img.shields.io/badge/Langflow-7528FC?logo=langchain&logoColor=white)](https://www.langflow.org)
[![Langfuse](https://img.shields.io/badge/Langfuse-0A0A0A?logo=opentelemetry&logoColor=white)](https://langfuse.com)
[![Lightdash](https://img.shields.io/badge/Lightdash-7262FF?logoColor=white)](https://www.lightdash.com)
[![LiteLLM](https://img.shields.io/badge/LiteLLM-00BFFF?logo=openai&logoColor=white)](https://www.litellm.ai)
[![Mage](https://img.shields.io/badge/Mage-6B4FBB?logo=mage&logoColor=white)](https://mage.ai)
[![Mailpit](https://img.shields.io/badge/Mailpit-F36F21?logo=maildotru&logoColor=white)](https://mailpit.axllent.org)
[![Marimo](https://img.shields.io/badge/Marimo-1C1C1C?logo=python&logoColor=white)](https://marimo.io)
[![Marmot](https://img.shields.io/badge/Marmot-8B5CF6?logoColor=white)](https://marmotdata.io)
[![Marquez](https://img.shields.io/badge/Marquez-1F5C99?logo=apacheairflow&logoColor=white)](https://marquezproject.ai)
[![Mathesar](https://img.shields.io/badge/Mathesar-5EBA7D?logoColor=white)](https://mathesar.org)
[![Meilisearch](https://img.shields.io/badge/Meilisearch-FF5CAA?logo=meilisearch&logoColor=white)](https://www.meilisearch.com)
[![Meltano](https://img.shields.io/badge/Meltano-512EFF?logo=meltano&logoColor=white)](https://meltano.com)
[![Memgraph](https://img.shields.io/badge/Memgraph-FB6E00?logo=memgraph&logoColor=white)](https://memgraph.com)
[![Metabase](https://img.shields.io/badge/Metabase-509EE3?logo=metabase&logoColor=white)](https://www.metabase.com)
[![Milvus](https://img.shields.io/badge/Milvus-00A1EA?logo=milvus&logoColor=white)](https://milvus.io)
[![MindsDB](https://img.shields.io/badge/MindsDB-00A3E0?logo=databricks&logoColor=white)](https://mindsdb.com)
[![MLflow](https://img.shields.io/badge/MLflow-0194E2?logo=mlflow&logoColor=white)](https://mlflow.org)
[![MongoDB](https://img.shields.io/badge/MongoDB-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com)
[![Mosquitto](https://img.shields.io/badge/Mosquitto-3C5280?logo=eclipsemosquitto&logoColor=white)](https://mosquitto.org)
[![MySQL](https://img.shields.io/badge/MySQL-4479A1?logo=mysql&logoColor=white)](https://www.mysql.com)
[![n8n](https://img.shields.io/badge/n8n-EA4B71?logo=n8n&logoColor=white)](https://n8n.io)
[![NATS](https://img.shields.io/badge/NATS-27AAE1?logo=natsdotio&logoColor=white)](https://nats.io)
[![Neo4j](https://img.shields.io/badge/Neo4j-4581C3?logo=neo4j&logoColor=white)](https://neo4j.com)
[![NocoDB](https://img.shields.io/badge/NocoDB-1F2937?logo=nocodb&logoColor=white)](https://nocodb.com)
[![Node-RED](https://img.shields.io/badge/Node--RED-8F0000?logo=nodered&logoColor=white)](https://nodered.org)
[![Nussknacker](https://img.shields.io/badge/Nussknacker-1E88E5?logo=apacheflink&logoColor=white)](https://nussknacker.io)
[![ODD Platform](https://img.shields.io/badge/ODD_Platform-2563EB?logoColor=white)](https://opendatadiscovery.org)
[![Ollama](https://img.shields.io/badge/Ollama-000000?logo=ollama&logoColor=white)](https://ollama.com)
[![Open Notebook](https://img.shields.io/badge/Open_Notebook-111827?logo=jupyter&logoColor=white)](https://github.com/lfnovo/open-notebook)
[![OpenBao](https://img.shields.io/badge/OpenBao-1F2937?logo=vault&logoColor=white)](https://openbao.org)
[![OpenMetadata](https://img.shields.io/badge/OpenMetadata-7147E8?logoColor=white)](https://open-metadata.org)
[![OpenSearch](https://img.shields.io/badge/OpenSearch-005EB8?logo=opensearch&logoColor=white)](https://opensearch.org)
[![Oracle Database Free](https://img.shields.io/badge/Oracle_Database_Free-F80000?logo=oracle&logoColor=white)](https://www.oracle.com/database/free/)
[![ParadeDB](https://img.shields.io/badge/ParadeDB-1C1C1C?logo=postgresql&logoColor=white)](https://www.paradedb.com)
[![Perplexica](https://img.shields.io/badge/Perplexica-1F2937?logoColor=white)](https://github.com/ItzCrazyKns/Perplexica)
[![pg_ducklake](https://img.shields.io/badge/pg__ducklake-336791?logo=postgresql&logoColor=white)](https://pgducklake.select)
[![pgAdmin](https://img.shields.io/badge/pgAdmin-336791?logo=postgresql&logoColor=white)](https://www.pgadmin.org)
[![Planka](https://img.shields.io/badge/Planka-4D4D4D?logo=planka&logoColor=white)](https://planka.app)
[![Portainer](https://img.shields.io/badge/Portainer-13BEF9?logo=portainer&logoColor=white)](https://www.portainer.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![PostgREST](https://img.shields.io/badge/PostgREST-2C3E50?logo=postgresql&logoColor=white)](https://postgrest.org)
[![Prefect](https://img.shields.io/badge/Prefect-024DFD?logo=prefect&logoColor=white)](https://www.prefect.io)
[![Presidio](https://img.shields.io/badge/Presidio-0078D4?logoColor=white)](https://microsoft.github.io/presidio/)
[![Project Nessie](https://img.shields.io/badge/Project_Nessie-0B2A4A?logoColor=white)](https://projectnessie.org)
[![Qdrant](https://img.shields.io/badge/Qdrant-DC244C?logo=qdrant&logoColor=white)](https://qdrant.tech)
[![QuestDB](https://img.shields.io/badge/QuestDB-D14671?logo=questdb&logoColor=white)](https://questdb.com)
[![Quickwit](https://img.shields.io/badge/Quickwit-FF6B6B?logo=quickwit&logoColor=white)](https://quickwit.io)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com)
[![Ray](https://img.shields.io/badge/Ray-028CF0?logo=ray&logoColor=white)](https://www.ray.io)
[![Redpanda](https://img.shields.io/badge/Redpanda-E4405F?logo=redpanda&logoColor=white)](https://redpanda.com)
[![Redpanda Connect](https://img.shields.io/badge/Redpanda%20Connect-E4405F?logo=redpanda&logoColor=white)](https://redpanda.com)
[![Redpanda Console](https://img.shields.io/badge/Redpanda%20Console-E4405F?logo=redpanda&logoColor=white)](https://redpanda.com)
[![Redpanda Datagen](https://img.shields.io/badge/Redpanda%20Datagen-E4405F?logo=redpanda&logoColor=white)](https://redpanda.com)
[![Rill](https://img.shields.io/badge/Rill-1E40AF?logoColor=white)](https://www.rilldata.com)
[![RisingWave](https://img.shields.io/badge/RisingWave-0065FF?logoColor=white)](https://risingwave.com)
[![RStudio](https://img.shields.io/badge/RStudio-75AADB?logo=rstudioide&logoColor=white)](https://posit.co/products/open-source/rstudio-server/)
[![RustFS](https://img.shields.io/badge/RustFS-B7410E?logo=rust&logoColor=white)](https://rustfs.com)
[![S3 Manager](https://img.shields.io/badge/S3_Manager-2E7D32?logo=amazons3&logoColor=white)](https://github.com/cloudlena/s3manager)
[![SearXNG](https://img.shields.io/badge/SearXNG-3050FF?logo=searxng&logoColor=white)](https://docs.searxng.org)
[![SeaweedFS](https://img.shields.io/badge/SeaweedFS-4CAF50?logo=amazons3&logoColor=white)](https://seaweedfs.com)
[![SFTPGo](https://img.shields.io/badge/SFTPGo-2D3748?logo=files&logoColor=white)](https://sftpgo.com)
[![Shiny](https://img.shields.io/badge/Shiny-447099?logo=r&logoColor=white)](https://posit.co/products/open-source/shinyserver/)
[![Sling](https://img.shields.io/badge/Sling-FF6B35?logo=data&logoColor=white)](https://slingdata.io)
[![Soda](https://img.shields.io/badge/Soda-6C47FF?logo=database&logoColor=white)](https://www.soda.io)
[![Spark](https://img.shields.io/badge/Apache_Spark-E25A1C?logo=apachespark&logoColor=white)](https://spark.apache.org)
[![SQL Server](https://img.shields.io/badge/SQL_Server-CC2927?logoColor=white)](https://www.microsoft.com/sql-server)
[![SQLMesh](https://img.shields.io/badge/SQLMesh-6C47FF?logoColor=white)](https://sqlmesh.com)
[![StarRocks](https://img.shields.io/badge/StarRocks-1F4FFF?logo=apache&logoColor=white)](https://www.starrocks.io)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Superset](https://img.shields.io/badge/Apache_Superset-20A6A4?logo=apachesuperset&logoColor=white)](https://superset.apache.org)
[![SurrealDB](https://img.shields.io/badge/SurrealDB-FF00A0?logo=surrealdb&logoColor=white)](https://surrealdb.com)
[![Telegraf](https://img.shields.io/badge/Telegraf-22ADF6?logo=influxdb&logoColor=white)](https://www.influxdata.com/time-series-platform/telegraf/)
[![Temporal](https://img.shields.io/badge/Temporal-000000?logo=temporal&logoColor=white)](https://temporal.io)
[![TimescaleDB](https://img.shields.io/badge/TimescaleDB-FDB515?logo=timescale&logoColor=white)](https://www.tigerdata.com/timescaledb)
[![Trino](https://img.shields.io/badge/Trino-DD00A1?logo=trino&logoColor=white)](https://trino.io)
[![Unity Catalog](https://img.shields.io/badge/Unity%20Catalog-FF3621?logo=databricks&logoColor=white)](https://www.unitycatalog.io)
[![Uptime Kuma](https://img.shields.io/badge/Uptime%20Kuma-5CDD8B?logo=uptimekuma&logoColor=white)](https://uptime.kuma.pet)
[![Valkey](https://img.shields.io/badge/Valkey-6983FF?logoColor=white)](https://valkey.io)
[![Vector](https://img.shields.io/badge/Vector-3B2F63?logo=vector&logoColor=white)](https://vector.dev)
[![Weaviate](https://img.shields.io/badge/Weaviate-00C9A7?logo=weaviate&logoColor=white)](https://weaviate.io)
[![Wetty](https://img.shields.io/badge/Wetty-000000?logo=gnubash&logoColor=white)](https://github.com/butlerx/wetty)
[![Whisper ASR](https://img.shields.io/badge/Whisper_ASR-412991?logo=openai&logoColor=white)](https://ahmetoner.com/whisper-asr-webservice/)
[![Wiki.js](https://img.shields.io/badge/Wiki.js-1976D2?logo=wikidotjs&logoColor=white)](https://js.wiki)
[![Windmill](https://img.shields.io/badge/Windmill-3B82F6?logo=windowsterminal&logoColor=white)](https://www.windmill.dev)
[![Woodpecker CI](https://img.shields.io/badge/Woodpecker_CI-4CAF50?logo=woodpeckerci&logoColor=white)](https://woodpecker-ci.org)
[![ZenML](https://img.shields.io/badge/ZenML-431D93?logoColor=white)](https://www.zenml.io)
[![Zeppelin](https://img.shields.io/badge/Apache_Zeppelin-1D4E89?logo=apache&logoColor=white)](https://zeppelin.apache.org)

Forgejo, Grafana, Infisical, Portainer and SFTPGo are **core** and always on.
code-server, Kestra, Marimo and Spark are **proven**: promised to work on every
release, across a teardown and restore. Everything else is best-effort.
[What each tier promises](docs/concepts/stacks.md#what-each-tier-promises) has
the details.

Entropy Data is the one stack under a proprietary licence; it is not open source.

[Browse the stack catalogue](docs/stacks/overview.md) for a description, the
pinned image version and a documentation page for every stack.

## Get started

You need a Hetzner Cloud account, a Cloudflare account with your domain on it,
and your own copy of this repository. Resend (email notifications) and Docker
Hub (higher pull limits) are optional.

1. Fork or import the repository.
2. Create the API tokens and add them as GitHub secrets.
3. Run the **Initial Setup** workflow.
4. Open `https://control.yourdomain.com` and sign in with the code sent to your email.

The [Setup Guide](docs/admin-guides/setup-guide.md) walks through every step.
Deployment runs in GitHub Actions only; there is no local deploy.

## Documentation

| Read this | When you want to |
|-----------|------------------|
| [Concepts](docs/concepts/index.md) | understand what it is and how it is built |
| [Setup Guide](docs/admin-guides/setup-guide.md) | deploy your own |
| [Control Plane guide](docs/user-guides/control-plane.md) | use a deployment someone set up for you |
| [Stack catalogue](docs/stacks/overview.md) | find a tool |
| [Tutorials](docs/tutorials/index.md) | learn by doing |
| [Troubleshooting](docs/admin-guides/troubleshooting.md) | fix something |

The same documentation is published at [nexus-stack.ch](https://nexus-stack.ch/docs/).

## Status and licence

Nexus-Stack is under active development. You are responsible for reviewing the
code and understanding what it does before you run it.

Released under the [MIT licence](LICENSE). Contributions are welcome, see
[CONTRIBUTING](docs/CONTRIBUTING.md).

Background reading:

- [Nexus-Stack: Your Data, Your Rules, Your Flow](https://stefanko-ch.medium.com/nexus-stack-your-data-your-rules-your-flow-46b29abc062d)
- [Secure Hetzner Docker Deployment via Cloudflare Zero Trust Tunnel](https://medium.com/@stefanko-ch/secure-hetzner-docker-deployment-via-cloudflare-zero-trust-tunnel-8f716c4631ce)
