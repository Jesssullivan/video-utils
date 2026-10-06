# Base-R plots for a verified report bundle. No package installation required.
# Reads only tables/events.csv, derived by scripts/report_bundle.py from the
# hash-bound analysis.json; it never reads media or the run directory.
abstain_plot <- function(message) {
  plot.new()
  text(0.5, 0.5, message)
  invisible(NULL)
}

plot_bundle_events <- function(bundle_dir) {
  path <- file.path(bundle_dir, "tables", "events.csv")
  if (!file.exists(path)) {
    return(abstain_plot("Source-bound event analysis unavailable or rejected"))
  }
  events <- read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
  column <- intersect(c("audio_relative_seconds", "time_s", "time_seconds", "time"), names(events))
  if (!length(column) || !nrow(events)) {
    return(abstain_plot("No timed events exported"))
  }
  times <- suppressWarnings(as.numeric(events[[column[1]]]))
  kinds <- intersect(c("kind", "type", "event_type"), names(events))
  labels <- if (length(kinds)) events[[kinds[1]]] else rep("onset", length(times))
  keep <- is.finite(times) & times >= 0
  times <- times[keep]
  labels <- labels[keep]
  if (!length(times)) {
    return(abstain_plot("No finite event times exported"))
  }
  groups <- unique(labels)
  old <- par(mar = c(4.5, 16, 3, 1))
  on.exit(par(old))
  plot(times, match(labels, groups), pch = "|", col = "#8a6a2f",
       xlab = "Seconds from decoded audio origin", ylab = "",
       yaxt = "n", ylim = c(0.5, length(groups) + 0.5),
       main = "Detected event candidates (not notes, not verified clicks)")
  axis(2, seq_along(groups), groups, las = 1, cex.axis = 0.75)
  invisible(events)
}
