package com.routefood.app.data.repository;

import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;
import com.routefood.app.core.firebase.FirebaseRefs;
import com.routefood.app.data.model.UserProfile;

public class UserRepository {
    private final FirebaseRefs refs;

    public UserRepository() {
        refs = new FirebaseRefs();
    }

    public void loadCurrentUser(RepositoryCallback<UserProfile> callback) {
        FirebaseUser user = FirebaseAuth.getInstance().getCurrentUser();
        if (user == null) {
            callback.onError(new IllegalStateException("No signed-in user."));
            return;
        }
        refs.users().document(user.getUid()).get()
                .addOnSuccessListener(document -> callback.onSuccess(new UserProfile(
                        user.getUid(),
                        document.getString("role"),
                        document.getString("displayName"),
                        document.getString("phone"),
                        document.getString("avatarUrl"),
                        Boolean.TRUE.equals(document.getBoolean("isBlocked")))))
                .addOnFailureListener(callback::onError);
    }
}
