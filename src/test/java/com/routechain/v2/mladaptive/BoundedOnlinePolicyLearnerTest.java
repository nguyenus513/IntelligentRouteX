package com.routechain.v2.mladaptive;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BoundedOnlinePolicyLearnerTest {
    @TempDir
    Path tempDir;

    @Test
    void shadow_mode_learns_but_never_applies_hint() {
        BoundedOnlinePolicyLearner learner = new BoundedOnlinePolicyLearner();
        learner.configure(new BoundedOnlinePolicyLearner.Config(true, true, 16, 4, 128, 10, 0.0));
        BoundedOnlinePolicyLearner.BatchContext context = new BoundedOnlinePolicyLearner.BatchContext("load-low", "urgency-normal", "age-fresh", "bad-low", "sim-high");
        learner.observe(new BoundedOnlinePolicyLearner.BatchDecision("d1", true, true, "load-low|urgency-normal|age-fresh|bad-low|sim-high", "batch:11", 10, 11, false, 0, 0, 0, "test"), goodOutcome());

        BoundedOnlinePolicyLearner.BatchDecision decision = learner.suggestBatchSize(context, 10, 20);

        assertTrue(decision.shadowOnly());
        assertFalse(decision.appliedAsHint());
        assertEquals(11, decision.suggestedBatchSize());
    }

    @Test
    void assist_mode_applies_only_bounded_batch_delta() {
        BoundedOnlinePolicyLearner learner = new BoundedOnlinePolicyLearner();
        learner.configure(new BoundedOnlinePolicyLearner.Config(true, false, 16, 4, 128, 10, 0.0));
        String contextKey = "load-med|urgency-hot|age-warm|bad-med|sim-med";
        BoundedOnlinePolicyLearner.BatchContext context = new BoundedOnlinePolicyLearner.BatchContext("load-med", "urgency-hot", "age-warm", "bad-med", "sim-med");
        learner.observe(new BoundedOnlinePolicyLearner.BatchDecision("d1", true, false, contextKey, "batch:11", 10, 11, true, 0, 0, 0, "test"), goodOutcome());

        BoundedOnlinePolicyLearner.BatchDecision decision = learner.suggestBatchSize(context, 10, 20);

        assertTrue(decision.appliedAsHint());
        assertEquals(11, decision.suggestedBatchSize());
    }

    @Test
    void compaction_keeps_state_bounded() {
        BoundedOnlinePolicyLearner learner = new BoundedOnlinePolicyLearner();
        learner.configure(new BoundedOnlinePolicyLearner.Config(true, false, 8, 3, 64, 10, 0.0));
        for (int i = 0; i < 30; i++) {
            String contextKey = "load-" + i + "|urgency-normal|age-fresh|bad-low|sim-high";
            learner.observe(new BoundedOnlinePolicyLearner.BatchDecision("d" + i, true, false, contextKey, "batch:10", 10, 10, false, 0, 0, 0, "test"), goodOutcome());
        }

        BoundedOnlinePolicyLearner.Snapshot snapshot = learner.snapshot();

        assertTrue(snapshot.contextCount() <= 8);
        assertTrue(snapshot.actionCount() <= 24);
        assertTrue(snapshot.stateSizeKb() <= 64);
        assertTrue(snapshot.evictedContextCount() > 0);
    }

    @Test
    void snapshot_roundtrip_preserves_policy_state() throws Exception {
        Path stateFile = tempDir.resolve("policy-state.json");
        BoundedOnlinePolicyLearner learner = new BoundedOnlinePolicyLearner();
        learner.configure(new BoundedOnlinePolicyLearner.Config(true, false, 16, 4, 128, 10, 0.0));
        String contextKey = "load-high|urgency-urgent|age-old|bad-high|sim-low";
        learner.observe(new BoundedOnlinePolicyLearner.BatchDecision("d1", true, false, contextKey, "batch:9", 10, 9, true, 0, 0, 0, "test"), goodOutcome());
        learner.save(stateFile);

        BoundedOnlinePolicyLearner restored = new BoundedOnlinePolicyLearner();
        restored.configure(new BoundedOnlinePolicyLearner.Config(true, false, 16, 4, 128, 10, 0.0));
        restored.load(stateFile);

        assertEquals(1, restored.snapshot().contextCount());
        assertEquals(1, restored.snapshot().actionCount());
    }

    private BoundedOnlinePolicyLearner.Outcome goodOutcome() {
        return new BoundedOnlinePolicyLearner.Outcome(1.0, 1.0, 0.0, 30.0, 25L, false, false, false);
    }
}
