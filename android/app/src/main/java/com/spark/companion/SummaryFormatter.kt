package com.spark.companion

import java.util.Locale

object SummaryFormatter {
    fun render(steps: Long, distanceKm: Double, activities: Int): String {
        require(steps >= 0L && distanceKm.isFinite() && distanceKm >= 0.0 && activities >= 0)
        return String.format(Locale.US, "Last 7 days\n\nActivities: %d\nSteps: %,d\nDistance: %.2f km",
            activities, steps, distanceKm)
    }
}
