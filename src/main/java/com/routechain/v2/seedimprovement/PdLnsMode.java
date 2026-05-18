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
    ML_HYBRID_PD_LNS;

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
                || this == ML_DESTROY_REPAIR_AUTO;
    }

    public int destroySize() {
        return switch (this) {
            case ML_DESTROY_REPAIR_K2 -> 2;
            case ML_DESTROY_REPAIR_K3 -> 3;
            case ML_DESTROY_REPAIR_K4 -> 4;
            case ML_DESTROY_REPAIR_AUTO, ML_DESTROY_REPAIR -> 0;
            default -> 1;
        };
    }
}
