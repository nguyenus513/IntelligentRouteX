package com.routefood.app.core.supabase;

import com.routefood.app.BuildConfig;

public final class SupabaseConfig {
    private SupabaseConfig() {
    }

    public static String url() {
        return BuildConfig.SUPABASE_URL;
    }

    public static String publishableKey() {
        return BuildConfig.SUPABASE_PUBLISHABLE_KEY;
    }

    public static boolean isConfigured() {
        return url() != null && url().startsWith("https://")
                && publishableKey() != null && publishableKey().startsWith("sb_publishable_");
    }
}
