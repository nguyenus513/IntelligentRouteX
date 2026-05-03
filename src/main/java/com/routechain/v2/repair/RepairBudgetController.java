package com.routechain.v2.repair;

import java.time.Duration;

public final class RepairBudgetController {
    private final long startedAtNanos;
    private final long budgetNanos;
    private final int maxIterations;

    public RepairBudgetController(Duration budget, int maxIterations) {
        this.startedAtNanos = System.nanoTime();
        this.budgetNanos = Math.max(1L, budget.toNanos());
        this.maxIterations = Math.max(1, maxIterations);
    }

    public boolean canContinue(int iteration) {
        return iteration < maxIterations && System.nanoTime() - startedAtNanos <= budgetNanos;
    }

    public Duration remainingBudget() {
        long elapsedNanos = System.nanoTime() - startedAtNanos;
        long remainingNanos = Math.max(1L, budgetNanos - elapsedNanos);
        return Duration.ofNanos(remainingNanos);
    }

    public boolean exhausted(int iteration) {
        return iteration >= maxIterations || System.nanoTime() - startedAtNanos > budgetNanos;
    }

    public long elapsedMillis() {
        return Math.max(0L, (System.nanoTime() - startedAtNanos) / 1_000_000L);
    }
}
