package com.routechain.api.bigdata;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "routechain.bigdata-lite.postgres")
public final class BigDataLitePostgresProperties {
    private boolean enabled = false;
    private String url = "jdbc:postgresql://localhost:5432/irx";
    private String username = "irx";
    private String password = "irx";

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public String getUrl() { return url; }
    public void setUrl(String url) { this.url = url; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
}
