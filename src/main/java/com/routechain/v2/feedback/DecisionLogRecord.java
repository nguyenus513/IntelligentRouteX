package com.routechain.v2.feedback;

import com.routechain.v2.EtaContext;
import com.routechain.v2.LiveStageMetadata;
import com.routechain.v2.MlStageMetadata;
import com.routechain.v2.SchemaVersioned;
import com.routechain.v2.DispatchLatencyBudgetSummary;
import com.routechain.v2.DispatchStageLatency;
import com.routechain.v2.cluster.MicroClusterSummary;
import com.routechain.v2.cluster.PairGraphSummary;
import com.routechain.v2.bundle.BundlePoolSummary;
import com.routechain.v2.executor.DispatchExecutionSummary;
import com.routechain.v2.route.DriverShortlistSummary;
import com.routechain.v2.route.PickupAnchorSummary;
import com.routechain.v2.route.RouteProposalSummary;
import com.routechain.v2.scenario.ScenarioEvaluationSummary;
import com.routechain.v2.selector.GlobalSelectorSummary;

import java.time.Instant;
import java.util.List;

public record DecisionLogRecord(
        String schemaVersion,
        String traceId,
        Instant decisionTime,
        List<String> decisionStages,
        boolean fallbackUsed,
        List<String> degradeReasons,
        EtaContext etaSummary,
        PairGraphSummary pairGraphSummary,
        MicroClusterSummary microClusterSummary,
        BundlePoolSummary bundlePoolSummary,
        PickupAnchorSummary pickupAnchorSummary,
        DriverShortlistSummary driverShortlistSummary,
        RouteProposalSummary routeProposalSummary,
        ScenarioEvaluationSummary scenarioEvaluationSummary,
        GlobalSelectorSummary globalSelectorSummary,
        DispatchExecutionSummary dispatchExecutionSummary,
        List<DispatchStageLatency> stageLatencies,
        DispatchLatencyBudgetSummary latencyBudgetSummary,
        List<MlStageMetadata> mlStageMetadata,
        List<MlContributionTrace> mlContributionTrace,
        List<LiveStageMetadata> liveStageMetadata,
        List<String> selectedProposalIds,
        List<String> executedAssignmentIds) implements SchemaVersioned {
}
