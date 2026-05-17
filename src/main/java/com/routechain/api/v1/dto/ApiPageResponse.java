package com.routechain.api.v1.dto;

import java.util.List;

public record ApiPageResponse<T>(List<T> items, int count, String nextPageToken) { }
