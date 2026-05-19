package com.routechain.v2.seedimprovement;

public enum PdLnsMode {
    OFF,
    BEST_SEED_ONLY,
    HEURISTIC_PD_LNS,
    ML_DESTROY_REPAIR,
    ML_DESTROY_REPAIR_K2,
    ML_DESTROY_REPAIR_K3,
    ML_DESTROY_REPAIR_K4,
    ML_DESTROY_REPAIR_AUTO,
    ML_HYBRID_PD_LNS,
    FULL_ML_PD_LNS,
    POLICY_ONLY_PD_LNS,
    MODEL_ASSISTED_PD_LNS,
    ML_CORE_PD_LNS,
    NO_ML_RANDOMIZED_PD_LNS,
    TABULAR_SCORED_PD_LNS,
    TABULAR_WEIGHT_025,
    TABULAR_WEIGHT_050,
    TABULAR_WEIGHT_075,
    TABULAR_ONLY_SCORER,
    ROUTEFINDER_ASSISTED_PD_LNS,
    TABULAR_ROUTEFINDER_PD_LNS,
    TABULAR_ROUTEFINDER_BASELINE,
    GREEDRL_CONTROLLER_PD_LNS,
    NO_GREEDRL,
    NO_ROUTEFINDER_PD_LNS,
    NO_TABULAR_PD_LNS,
    NO_ADAPTIVE_POLICY,
    NO_ADAPTIVE_MOVE_PRIORITY,
    NO_ADAPTIVE_OPERATOR_POLICY,
    NO_REWARD_UPDATE;

    public static PdLnsMode from(String value) {
        if (value == null || value.isBlank()) {
            return OFF;
        }
        try {
            return PdLnsMode.valueOf(value.trim().toUpperCase());
        } catch (IllegalArgumentException ignored) {
            return OFF;
        }
    }

    public boolean mlDestroyRepair() {
        return this == ML_DESTROY_REPAIR
                || this == ML_DESTROY_REPAIR_K2
                || this == ML_DESTROY_REPAIR_K3
                || this == ML_DESTROY_REPAIR_K4
                || this == ML_DESTROY_REPAIR_AUTO
                || this == FULL_ML_PD_LNS
                || this == POLICY_ONLY_PD_LNS
                || this == MODEL_ASSISTED_PD_LNS
                || this == ML_CORE_PD_LNS
                || this == NO_ML_RANDOMIZED_PD_LNS
                || this == TABULAR_SCORED_PD_LNS
                || this == TABULAR_WEIGHT_025
                || this == TABULAR_WEIGHT_050
                || this == TABULAR_WEIGHT_075
                || this == TABULAR_ONLY_SCORER
                || this == ROUTEFINDER_ASSISTED_PD_LNS
                || this == TABULAR_ROUTEFINDER_PD_LNS
                || this == TABULAR_ROUTEFINDER_BASELINE
                || this == GREEDRL_CONTROLLER_PD_LNS
                || this == NO_GREEDRL
                || this == NO_ROUTEFINDER_PD_LNS
                || this == NO_TABULAR_PD_LNS
                || this == NO_ADAPTIVE_POLICY
                || this == NO_ADAPTIVE_MOVE_PRIORITY
                || this == NO_ADAPTIVE_OPERATOR_POLICY
                || this == NO_REWARD_UPDATE;
    }

    public boolean hybridPdLns() {
        return this == ML_HYBRID_PD_LNS
                || this == FULL_ML_PD_LNS
                || this == POLICY_ONLY_PD_LNS
                || this == MODEL_ASSISTED_PD_LNS
                || this == ML_CORE_PD_LNS
                || this == TABULAR_SCORED_PD_LNS
                || this == TABULAR_WEIGHT_025
                || this == TABULAR_WEIGHT_050
                || this == TABULAR_WEIGHT_075
                || this == TABULAR_ONLY_SCORER
                || this == ROUTEFINDER_ASSISTED_PD_LNS
                || this == TABULAR_ROUTEFINDER_PD_LNS
                || this == TABULAR_ROUTEFINDER_BASELINE
                || this == GREEDRL_CONTROLLER_PD_LNS
                || this == NO_GREEDRL
                || this == NO_ROUTEFINDER_PD_LNS
                || this == NO_TABULAR_PD_LNS
                || this == NO_REWARD_UPDATE;
    }

    public boolean tabularScored() {
        return this == MODEL_ASSISTED_PD_LNS
                || this == ML_CORE_PD_LNS
                || this == TABULAR_SCORED_PD_LNS
                || this == TABULAR_WEIGHT_025
                || this == TABULAR_WEIGHT_050
                || this == TABULAR_WEIGHT_075
                || this == TABULAR_ONLY_SCORER
                || this == TABULAR_ROUTEFINDER_PD_LNS
                || this == TABULAR_ROUTEFINDER_BASELINE
                || this == GREEDRL_CONTROLLER_PD_LNS
                || this == NO_GREEDRL;
    }

    public boolean routefinderAssisted() {
        return this == ROUTEFINDER_ASSISTED_PD_LNS
                || this == TABULAR_ROUTEFINDER_PD_LNS
                || this == TABULAR_ROUTEFINDER_BASELINE
                || this == GREEDRL_CONTROLLER_PD_LNS
                || this == NO_GREEDRL;
    }

    public boolean greedRlControlled() {
        return this == GREEDRL_CONTROLLER_PD_LNS;
    }

    public double tabularWeight() {
        return switch (this) {
            case TABULAR_WEIGHT_025 -> 0.25;
            case TABULAR_WEIGHT_050, TABULAR_SCORED_PD_LNS, MODEL_ASSISTED_PD_LNS, ML_CORE_PD_LNS -> 0.50;
            case TABULAR_WEIGHT_075, TABULAR_ROUTEFINDER_PD_LNS, TABULAR_ROUTEFINDER_BASELINE, GREEDRL_CONTROLLER_PD_LNS, NO_GREEDRL -> 0.75;
            case TABULAR_ONLY_SCORER -> 1.00;
            default -> 0.0;
        };
    }

    public boolean policyAblation() {
        return this == NO_ADAPTIVE_POLICY
                || this == NO_ADAPTIVE_MOVE_PRIORITY
                || this == NO_ADAPTIVE_OPERATOR_POLICY
                || this == NO_REWARD_UPDATE;
    }

    public int destroySize() {
        return switch (this) {
            case ML_DESTROY_REPAIR_K2 -> 2;
            case ML_DESTROY_REPAIR_K3 -> 3;
            case ML_DESTROY_REPAIR_K4 -> 4;
            case ML_DESTROY_REPAIR_AUTO, ML_DESTROY_REPAIR, FULL_ML_PD_LNS, POLICY_ONLY_PD_LNS, MODEL_ASSISTED_PD_LNS, ML_CORE_PD_LNS, NO_ML_RANDOMIZED_PD_LNS, TABULAR_SCORED_PD_LNS, TABULAR_WEIGHT_025, TABULAR_WEIGHT_050, TABULAR_WEIGHT_075, TABULAR_ONLY_SCORER, ROUTEFINDER_ASSISTED_PD_LNS, TABULAR_ROUTEFINDER_PD_LNS, TABULAR_ROUTEFINDER_BASELINE, GREEDRL_CONTROLLER_PD_LNS, NO_GREEDRL, NO_ROUTEFINDER_PD_LNS, NO_TABULAR_PD_LNS, NO_ADAPTIVE_POLICY, NO_ADAPTIVE_MOVE_PRIORITY, NO_ADAPTIVE_OPERATOR_POLICY, NO_REWARD_UPDATE -> 0;
            default -> 1;
        };
    }
}
