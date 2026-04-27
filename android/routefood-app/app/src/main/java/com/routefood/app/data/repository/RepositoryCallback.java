package com.routefood.app.data.repository;

public interface RepositoryCallback<T> {
    void onSuccess(T value);

    void onError(Exception error);
}
