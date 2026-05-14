package com.routefood.app.core.auth;

import android.content.Context;

import com.google.android.gms.tasks.Task;
import com.google.firebase.FirebaseApp;
import com.google.firebase.auth.AuthResult;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;

public class AuthManager {
    private final FirebaseAuth firebaseAuth;
    private final SessionStore sessionStore;

    public AuthManager(Context context) {
        sessionStore = new SessionStore(context);
        FirebaseAuth auth = null;
        if (!FirebaseApp.getApps(context.getApplicationContext()).isEmpty()) {
            try {
                auth = FirebaseAuth.getInstance();
            } catch (IllegalStateException ignored) {
                auth = null;
            }
        }
        firebaseAuth = auth;
    }

    public boolean isFirebaseAvailable() {
        return firebaseAuth != null;
    }

    public FirebaseUser currentUser() {
        return firebaseAuth == null ? null : firebaseAuth.getCurrentUser();
    }

    public boolean hasSignedInUser() {
        return sessionStore.hasSupabaseSession() || currentUser() != null;
    }

    public String currentSupabaseUserId() {
        return sessionStore.getSupabaseUserId();
    }

    public String currentSupabaseAccessToken() {
        return sessionStore.getSupabaseAccessToken();
    }

    public Task<AuthResult> signIn(String email, String password) {
        if (firebaseAuth == null) {
            throw new IllegalStateException("Firebase Auth is not configured.");
        }
        return firebaseAuth.signInWithEmailAndPassword(email, password);
    }

    public Task<AuthResult> register(String email, String password) {
        if (firebaseAuth == null) {
            throw new IllegalStateException("Firebase Auth is not configured.");
        }
        return firebaseAuth.createUserWithEmailAndPassword(email, password);
    }

    public void signOut() {
        sessionStore.clearSupabaseSession();
        if (firebaseAuth != null) {
            firebaseAuth.signOut();
        }
    }
}
