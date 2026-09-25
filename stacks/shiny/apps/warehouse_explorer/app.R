# Browse the shared PostgreSQL and plot a query.
#
# Ships with the stack so that a fresh Shiny Server is not just the
# upstream sample apps, and so the connection to the shared `postgres`
# stack is demonstrated once rather than rediscovered in every app.

library(shiny)
library(DBI)
library(RPostgres)
library(ggplot2)
library(DT)

password <- Sys.getenv("POSTGRES_PASSWORD")
db_host <- Sys.getenv("POSTGRES_HOST", "postgres")

# Whether the host resolves at all on this Docker network. Worth telling
# apart from a connection failure: a name that does not resolve means the
# `postgres` stack is simply not enabled in this deployment, not that
# anything is broken. nsl() returns NULL rather than erroring.
host_is_deployed <- !is.null(nsl(db_host))

TABLES_SQL <- "
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name
"

# One connection per R process, opened lazily so the app still renders
# its message when there is no database to reach.
connect <- local({
  conn <- NULL
  function() {
    if (is.null(conn) || !dbIsValid(conn)) {
      conn <<- dbConnect(
        RPostgres::Postgres(),
        host = db_host,
        port = as.integer(Sys.getenv("POSTGRES_PORT", "5432")),
        dbname = Sys.getenv("POSTGRES_DB", "postgres"),
        user = Sys.getenv("POSTGRES_USER", "nexus-postgres"),
        password = password,
        connect_timeout = 5
      )
      # Read-only at the session level: a guard against ACCIDENT, not a
      # security boundary. A mistyped UPDATE is refused by PostgreSQL rather
      # than by a check here, but it is a session DEFAULT and anyone typing
      # SQL can lift it with SET default_transaction_read_only = off —
      # measured. Acceptable because adminer and cloudbeaver already allow
      # writes outright to the same audience, and Cloudflare Access is what
      # decides who reaches any of them.
      dbExecute(conn, "SET default_transaction_read_only = on")
    }
    conn
  }
})

ui <- fluidPage(
  titlePanel("Warehouse explorer"),
  if (!host_is_deployed) {
    div(
      class = "alert alert-info",
      sprintf(
        paste0("The postgres stack is not running in this deployment, so ",
               "there is nothing for this example to explore \u2014 '%s' does ",
               "not resolve on the container network. Enable PostgreSQL in ",
               "the Control Plane and spin up again, or point this app at ",
               "another database with POSTGRES_HOST."),
        db_host
      )
    )
  } else if (!nzchar(password)) {
    div(
      class = "alert alert-warning",
      "No POSTGRES_PASSWORD in this container's environment, so there is ",
      "nothing to connect to. Enable the postgres stack in the Control ",
      "Plane and spin up again."
    )
  } else {
    fluidRow(
      column(
        4,
        h4("Tables"),
        DT::dataTableOutput("tables")
      ),
      column(
        8,
        h4("Query"),
        textAreaInput("sql", NULL, value = "SELECT version()", rows = 4, width = "100%"),
        actionButton("run", "Run", class = "btn-primary"),
        DT::dataTableOutput("result"),
        plotOutput("plot", height = "300px")
      )
    )
  }
)

server <- function(input, output, session) {
  if (!host_is_deployed || !nzchar(password)) {
    return(invisible(NULL))
  }

  tables <- reactive({
    tryCatch(dbGetQuery(connect(), TABLES_SQL), error = function(e) {
      showNotification(conditionMessage(e), type = "error", duration = NULL)
      data.frame()
    })
  })

  output$tables <- DT::renderDataTable(
    DT::datatable(tables(), rownames = FALSE, options = list(dom = "tp", pageLength = 10))
  )

  # A default query the reader can run without typing: the first table
  # the database actually has.
  observe({
    first <- tables()
    if (nrow(first) > 0) {
      updateTextAreaInput(
        session, "sql",
        value = sprintf("SELECT * FROM %s.%s LIMIT 100", first[1, 1], first[1, 2])
      )
    }
  })

  result <- eventReactive(input$run, {
    tryCatch(dbGetQuery(connect(), input$sql), error = function(e) {
      showNotification(conditionMessage(e), type = "error", duration = NULL)
      NULL
    })
  })

  output$result <- DT::renderDataTable({
    req(result())
    DT::datatable(result(), rownames = FALSE, options = list(dom = "tp"))
  })

  output$plot <- renderPlot({
    df <- result()
    req(df, nrow(df) > 1)
    numeric_cols <- names(df)[vapply(df, is.numeric, logical(1))]
    req(length(numeric_cols) > 0)
    ggplot(df, aes(x = seq_len(nrow(df)), y = .data[[numeric_cols[1]]])) +
      geom_col(fill = "#447099") +
      labs(x = "row", y = numeric_cols[1]) +
      theme_minimal()
  })
}

shinyApp(ui, server)
