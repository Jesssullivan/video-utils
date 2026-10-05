# Base-R plots for the exported event table. No package installation required.
plot_run_events <- function(run_dir) {
  path <- file.path(run_dir, "events.csv")
  if (!file.exists(path)) {
    plot.new()
    text(0.5, 0.5, "Event analysis unavailable")
    return(invisible(NULL))
  }
  events <- read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
  column <- intersect(c("audio_relative_seconds", "time_s", "time_seconds", "time"), names(events))
  if (!length(column) || !nrow(events)) {
    plot.new()
    text(0.5, 0.5, "No timed events exported")
    return(invisible(NULL))
  }
  times <- suppressWarnings(as.numeric(events[[column[1]]]))
  kinds <- intersect(c("kind", "type", "event_type"), names(events))
  labels <- if (length(kinds)) events[[kinds[1]]] else rep("onset", length(times))
  keep <- is.finite(times) & times >= 0
  times <- times[keep]
  labels <- labels[keep]
  if (!length(times)) {
    plot.new()
    text(0.5, 0.5, "No finite event times exported")
    return(invisible(NULL))
  }
  groups <- unique(labels)
  plot(times, match(labels, groups), pch = 16, col = "#b68c46",
       xlab = "Seconds from decoded audio origin", ylab = "",
       yaxt = "n", ylim = c(0.5, length(groups) + 0.5),
       main = "Detected event candidates")
  axis(2, seq_along(groups), groups, las = 1)
  invisible(events)
}
