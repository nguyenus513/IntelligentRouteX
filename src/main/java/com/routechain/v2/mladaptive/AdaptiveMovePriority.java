package com.routechain.v2.mladaptive;

import com.routechain.v2.hybrid.CandidateSource;
import com.routechain.v2.hybrid.MoveEvaluationTrace;

import java.util.Comparator;
import java.util.List;

public final class AdaptiveMovePriority {
    public RankedMoves rank(List<MoveEvaluationTrace> moves, CandidateSource seedSource, AdaptiveLearningState state, int topK) {
        if (moves == null || moves.isEmpty()) {
            return new RankedMoves(0, 0, 0, 0, 0.0, List.of());
        }
        List<MoveEvaluationTrace> ranked = moves.stream()
                .sorted(Comparator.comparingDouble((MoveEvaluationTrace move) -> score(move, seedSource, state)).reversed())
                .toList();
        int evaluated = Math.min(Math.max(1, topK), ranked.size());
        long accepted = ranked.stream().filter(MoveEvaluationTrace::accepted).count();
        long acceptedTopK = ranked.stream().limit(evaluated).filter(MoveEvaluationTrace::accepted).count();
        double acceptedRate = accepted / (double) Math.max(1, moves.size());
        return new RankedMoves(moves.size(), evaluated, (int) accepted, (int) acceptedTopK, round(acceptedRate), ranked.stream().limit(evaluated).map(MoveEvaluationTrace::moveId).toList());
    }

    private double score(MoveEvaluationTrace move, CandidateSource seedSource, AdaptiveLearningState state) {
        MovePatternKey key = MovePatternKey.from(move.moveType(), seedSource == null ? "UNKNOWN" : seedSource.name(), move.improvementKm());
        double latenessRisk = move.latenessTrace().isEmpty() ? 0.0 : 100.0;
        double rejectPenalty = move.accepted() ? 0.0 : 5.0;
        return move.improvementKm() * 10.0 - latenessRisk - rejectPenalty + state.movePatternReward(key);
    }

    private static double round(double value) {
        return Math.round(value * 1000.0) / 1000.0;
    }

    public record RankedMoves(int scoredMoves, int evaluatedTopK, int acceptedMoves, int acceptedFromTopK, double acceptedMoveRate, List<String> topMoveIds) {
    }
}
