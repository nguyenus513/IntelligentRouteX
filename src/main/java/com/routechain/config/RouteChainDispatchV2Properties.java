package com.routechain.config;

import com.routechain.v2.feedback.FeedbackStorageMode;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

@ConfigurationProperties(prefix = "routechain.dispatch-v2")
public class RouteChainDispatchV2Properties {
    private boolean enabled = false;
    private boolean mlEnabled = false;
    private boolean sidecarRequired = false;
    private boolean selectorOrtoolsEnabled = false;
    private boolean warmStartEnabled = true;
    private boolean hotStartEnabled = true;
    private boolean tomtomEnabled = false;
    private boolean openMeteoEnabled = true;
    private Duration tick = Duration.ofSeconds(30);
    private final Buffer buffer = new Buffer();
    private final Cluster cluster = new Cluster();
    private final Bundle bundle = new Bundle();
    private final Candidate candidate = new Candidate();
    private final Context context = new Context();
    private final Pair pair = new Pair();
    private final MicroCluster microCluster = new MicroCluster();
    private final BoundaryExpansion boundaryExpansion = new BoundaryExpansion();
    private final Scenario scenario = new Scenario();
    private final Selector selector = new Selector();
    private final Ml ml = new Ml();
    private final Weather weather = new Weather();
    private final Traffic traffic = new Traffic();
    private final Feedback feedback = new Feedback();
    private final Harvest harvest = new Harvest();
    private final WarmHotStart warmHotStart = new WarmHotStart();
    private final Performance performance = new Performance();
    private final Compute compute = new Compute();
    private final Decision decision = new Decision();
    private final Routing routing = new Routing();

    public static RouteChainDispatchV2Properties defaults() {
        return new RouteChainDispatchV2Properties();
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public boolean isMlEnabled() {
        return mlEnabled;
    }

    public void setMlEnabled(boolean mlEnabled) {
        this.mlEnabled = mlEnabled;
    }

    public boolean isSidecarRequired() {
        return sidecarRequired;
    }

    public void setSidecarRequired(boolean sidecarRequired) {
        this.sidecarRequired = sidecarRequired;
    }

    public boolean isSelectorOrtoolsEnabled() {
        return selectorOrtoolsEnabled;
    }

    public void setSelectorOrtoolsEnabled(boolean selectorOrtoolsEnabled) {
        this.selectorOrtoolsEnabled = selectorOrtoolsEnabled;
    }

    public boolean isWarmStartEnabled() {
        return warmStartEnabled;
    }

    public void setWarmStartEnabled(boolean warmStartEnabled) {
        this.warmStartEnabled = warmStartEnabled;
    }

    public boolean isHotStartEnabled() {
        return hotStartEnabled;
    }

    public void setHotStartEnabled(boolean hotStartEnabled) {
        this.hotStartEnabled = hotStartEnabled;
    }

    public boolean isTomtomEnabled() {
        return tomtomEnabled;
    }

    public void setTomtomEnabled(boolean tomtomEnabled) {
        this.tomtomEnabled = tomtomEnabled;
    }

    public boolean isOpenMeteoEnabled() {
        return openMeteoEnabled;
    }

    public void setOpenMeteoEnabled(boolean openMeteoEnabled) {
        this.openMeteoEnabled = openMeteoEnabled;
    }

    public Duration getTick() {
        return tick;
    }

    public void setTick(Duration tick) {
        this.tick = tick;
    }

    public Buffer getBuffer() {
        return buffer;
    }

    public Cluster getCluster() {
        return cluster;
    }

    public Bundle getBundle() {
        return bundle;
    }

    public Candidate getCandidate() {
        return candidate;
    }

    public Context getContext() {
        return context;
    }

    public Pair getPair() {
        return pair;
    }

    public MicroCluster getMicroCluster() {
        return microCluster;
    }

    public BoundaryExpansion getBoundaryExpansion() {
        return boundaryExpansion;
    }

    public Scenario getScenario() {
        return scenario;
    }

    public Selector getSelector() {
        return selector;
    }

    public Ml getMl() {
        return ml;
    }

    public Weather getWeather() {
        return weather;
    }

    public Traffic getTraffic() {
        return traffic;
    }

    public Feedback getFeedback() {
        return feedback;
    }

    public Harvest getHarvest() {
        return harvest;
    }

    public WarmHotStart getWarmHotStart() {
        return warmHotStart;
    }

    public Performance getPerformance() {
        return performance;
    }

    public Compute getCompute() {
        return compute;
    }

    public Decision getDecision() {
        return decision;
    }

    public Routing getRouting() {
        return routing;
    }

    public static final class Routing {
        private String provider = "synthetic";
        private int refineLimitPerTick = 24;
        private Duration connectTimeout = Duration.ofSeconds(2);
        private Duration readTimeout = Duration.ofSeconds(5);

        public String getProvider() {
            return provider;
        }

        public void setProvider(String provider) {
            this.provider = provider;
        }

        public int getRefineLimitPerTick() {
            return refineLimitPerTick;
        }

        public void setRefineLimitPerTick(int refineLimitPerTick) {
            this.refineLimitPerTick = refineLimitPerTick;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public Duration getReadTimeout() {
            return readTimeout;
        }

        public void setReadTimeout(Duration readTimeout) {
            this.readTimeout = readTimeout;
        }
    }

    public static final class Buffer {
        private Duration holdWindow = Duration.ofSeconds(45);

        public Duration getHoldWindow() {
            return holdWindow;
        }

        public void setHoldWindow(Duration holdWindow) {
            this.holdWindow = holdWindow;
        }
    }

    public static final class Cluster {
        private int maxSize = 24;

        public int getMaxSize() {
            return maxSize;
        }

        public void setMaxSize(int maxSize) {
            this.maxSize = maxSize;
        }
    }

    public static final class Bundle {
        private int minSize = 2;
        private int maxSize = 5;
        private int topNeighbors = 12;
        private int beamWidth = 16;

        public int getMinSize() {
            return minSize;
        }

        public void setMinSize(int minSize) {
            this.minSize = minSize;
        }

        public int getMaxSize() {
            return maxSize;
        }

        public void setMaxSize(int maxSize) {
            this.maxSize = maxSize;
        }

        public int getTopNeighbors() {
            return topNeighbors;
        }

        public void setTopNeighbors(int topNeighbors) {
            this.topNeighbors = topNeighbors;
        }

        public int getBeamWidth() {
            return beamWidth;
        }

        public void setBeamWidth(int beamWidth) {
            this.beamWidth = beamWidth;
        }
    }

    public static final class Candidate {
        private int maxAnchors = 3;
        private int maxDrivers = 8;
        private int maxRouteAlternatives = 4;
        private final RouteProposalBudget routeProposalBudget = new RouteProposalBudget();

        public int getMaxAnchors() {
            return maxAnchors;
        }

        public void setMaxAnchors(int maxAnchors) {
            this.maxAnchors = maxAnchors;
        }

        public int getMaxDrivers() {
            return maxDrivers;
        }

        public void setMaxDrivers(int maxDrivers) {
            this.maxDrivers = maxDrivers;
        }

        public int getMaxRouteAlternatives() {
            return maxRouteAlternatives;
        }

        public void setMaxRouteAlternatives(int maxRouteAlternatives) {
            this.maxRouteAlternatives = maxRouteAlternatives;
        }

        public RouteProposalBudget getRouteProposalBudget() {
            return routeProposalBudget;
        }

        public static final class RouteProposalBudget {
            private boolean enabled = false;
            private int localLiteMaxTotal = 128;
            private int fullAdaptiveSMaxTotal = 256;
            private int fullAdaptiveMMaxTotal = 512;
            private int maxDriversPerBundle = 4;
            private int maxAnchorsPerBundle = 2;
            private int maxAlternativesPerTuple = 2;
            private double lowGeometryCoverageThreshold = 0.75;
            private double lowGeometryCoverageBreadthMultiplier = 0.70;
            private String workloadSizeHint = "";

            public boolean isEnabled() {
                return enabled;
            }

            public void setEnabled(boolean enabled) {
                this.enabled = enabled;
            }

            public int getLocalLiteMaxTotal() {
                return localLiteMaxTotal;
            }

            public void setLocalLiteMaxTotal(int localLiteMaxTotal) {
                this.localLiteMaxTotal = localLiteMaxTotal;
            }

            public int getFullAdaptiveSMaxTotal() {
                return fullAdaptiveSMaxTotal;
            }

            public void setFullAdaptiveSMaxTotal(int fullAdaptiveSMaxTotal) {
                this.fullAdaptiveSMaxTotal = fullAdaptiveSMaxTotal;
            }

            public int getFullAdaptiveMMaxTotal() {
                return fullAdaptiveMMaxTotal;
            }

            public void setFullAdaptiveMMaxTotal(int fullAdaptiveMMaxTotal) {
                this.fullAdaptiveMMaxTotal = fullAdaptiveMMaxTotal;
            }

            public int getMaxDriversPerBundle() {
                return maxDriversPerBundle;
            }

            public void setMaxDriversPerBundle(int maxDriversPerBundle) {
                this.maxDriversPerBundle = maxDriversPerBundle;
            }

            public int getMaxAnchorsPerBundle() {
                return maxAnchorsPerBundle;
            }

            public void setMaxAnchorsPerBundle(int maxAnchorsPerBundle) {
                this.maxAnchorsPerBundle = maxAnchorsPerBundle;
            }

            public int getMaxAlternativesPerTuple() {
                return maxAlternativesPerTuple;
            }

            public void setMaxAlternativesPerTuple(int maxAlternativesPerTuple) {
                this.maxAlternativesPerTuple = maxAlternativesPerTuple;
            }

            public double getLowGeometryCoverageThreshold() {
                return lowGeometryCoverageThreshold;
            }

            public void setLowGeometryCoverageThreshold(double lowGeometryCoverageThreshold) {
                this.lowGeometryCoverageThreshold = lowGeometryCoverageThreshold;
            }

            public double getLowGeometryCoverageBreadthMultiplier() {
                return lowGeometryCoverageBreadthMultiplier;
            }

            public void setLowGeometryCoverageBreadthMultiplier(double lowGeometryCoverageBreadthMultiplier) {
                this.lowGeometryCoverageBreadthMultiplier = lowGeometryCoverageBreadthMultiplier;
            }

            public String getWorkloadSizeHint() {
                return workloadSizeHint;
            }

            public void setWorkloadSizeHint(String workloadSizeHint) {
                this.workloadSizeHint = workloadSizeHint;
            }
        }
    }

    public static final class Context {
        private double baselineSpeedKph = 22.0;
        private double heavyRainMultiplier = 1.28;
        private double lightRainMultiplier = 1.07;
        private int tomtomRefineBudgetPerTick = 8;
        private final Freshness freshness = new Freshness();
        private final Timeouts timeouts = new Timeouts();

        public double getBaselineSpeedKph() {
            return baselineSpeedKph;
        }

        public void setBaselineSpeedKph(double baselineSpeedKph) {
            this.baselineSpeedKph = baselineSpeedKph;
        }

        public double getHeavyRainMultiplier() {
            return heavyRainMultiplier;
        }

        public void setHeavyRainMultiplier(double heavyRainMultiplier) {
            this.heavyRainMultiplier = heavyRainMultiplier;
        }

        public double getLightRainMultiplier() {
            return lightRainMultiplier;
        }

        public void setLightRainMultiplier(double lightRainMultiplier) {
            this.lightRainMultiplier = lightRainMultiplier;
        }

        public int getTomtomRefineBudgetPerTick() {
            return tomtomRefineBudgetPerTick;
        }

        public void setTomtomRefineBudgetPerTick(int tomtomRefineBudgetPerTick) {
            this.tomtomRefineBudgetPerTick = tomtomRefineBudgetPerTick;
        }

        public Freshness getFreshness() {
            return freshness;
        }

        public Timeouts getTimeouts() {
            return timeouts;
        }
    }

    public static final class Freshness {
        private Duration weatherMaxAge = Duration.ofMinutes(15);
        private Duration trafficMaxAge = Duration.ofMinutes(10);
        private Duration forecastMaxAge = Duration.ofMinutes(30);

        public Duration getWeatherMaxAge() {
            return weatherMaxAge;
        }

        public void setWeatherMaxAge(Duration weatherMaxAge) {
            this.weatherMaxAge = weatherMaxAge;
        }

        public Duration getTrafficMaxAge() {
            return trafficMaxAge;
        }

        public void setTrafficMaxAge(Duration trafficMaxAge) {
            this.trafficMaxAge = trafficMaxAge;
        }

        public Duration getForecastMaxAge() {
            return forecastMaxAge;
        }

        public void setForecastMaxAge(Duration forecastMaxAge) {
            this.forecastMaxAge = forecastMaxAge;
        }
    }

    public static final class Timeouts {
        private Duration etaMlTimeout = Duration.ofMillis(150);

        public Duration getEtaMlTimeout() {
            return etaMlTimeout;
        }

        public void setEtaMlTimeout(Duration etaMlTimeout) {
            this.etaMlTimeout = etaMlTimeout;
        }
    }

    public static final class Pair {
        private double pickupDistanceKmThreshold = 2.2;
        private int readyGapMinutesThreshold = 15;
        private double dropAngleDiffDegreesThreshold = 55.0;
        private double mergeEtaRatioThreshold = 1.25;
        private double scoreThreshold = 0.45;
        private Duration mlTimeout = Duration.ofMillis(120);
        private int maxCandidateNeighborsPerOrder = 12;
        private final WeatherTightened weatherTightened = new WeatherTightened();

        public double getPickupDistanceKmThreshold() {
            return pickupDistanceKmThreshold;
        }

        public void setPickupDistanceKmThreshold(double pickupDistanceKmThreshold) {
            this.pickupDistanceKmThreshold = pickupDistanceKmThreshold;
        }

        public int getReadyGapMinutesThreshold() {
            return readyGapMinutesThreshold;
        }

        public void setReadyGapMinutesThreshold(int readyGapMinutesThreshold) {
            this.readyGapMinutesThreshold = readyGapMinutesThreshold;
        }

        public double getDropAngleDiffDegreesThreshold() {
            return dropAngleDiffDegreesThreshold;
        }

        public void setDropAngleDiffDegreesThreshold(double dropAngleDiffDegreesThreshold) {
            this.dropAngleDiffDegreesThreshold = dropAngleDiffDegreesThreshold;
        }

        public double getMergeEtaRatioThreshold() {
            return mergeEtaRatioThreshold;
        }

        public void setMergeEtaRatioThreshold(double mergeEtaRatioThreshold) {
            this.mergeEtaRatioThreshold = mergeEtaRatioThreshold;
        }

        public double getScoreThreshold() {
            return scoreThreshold;
        }

        public void setScoreThreshold(double scoreThreshold) {
            this.scoreThreshold = scoreThreshold;
        }

        public Duration getMlTimeout() {
            return mlTimeout;
        }

        public void setMlTimeout(Duration mlTimeout) {
            this.mlTimeout = mlTimeout;
        }

        public int getMaxCandidateNeighborsPerOrder() {
            return maxCandidateNeighborsPerOrder;
        }

        public void setMaxCandidateNeighborsPerOrder(int maxCandidateNeighborsPerOrder) {
            this.maxCandidateNeighborsPerOrder = maxCandidateNeighborsPerOrder;
        }

        public WeatherTightened getWeatherTightened() {
            return weatherTightened;
        }
    }

    public static final class WeatherTightened {
        private double pickupDistanceKmThreshold = 1.4;
        private int readyGapMinutesThreshold = 10;
        private double mergeEtaRatioThreshold = 1.15;

        public double getPickupDistanceKmThreshold() {
            return pickupDistanceKmThreshold;
        }

        public void setPickupDistanceKmThreshold(double pickupDistanceKmThreshold) {
            this.pickupDistanceKmThreshold = pickupDistanceKmThreshold;
        }

        public int getReadyGapMinutesThreshold() {
            return readyGapMinutesThreshold;
        }

        public void setReadyGapMinutesThreshold(int readyGapMinutesThreshold) {
            this.readyGapMinutesThreshold = readyGapMinutesThreshold;
        }

        public double getMergeEtaRatioThreshold() {
            return mergeEtaRatioThreshold;
        }

        public void setMergeEtaRatioThreshold(double mergeEtaRatioThreshold) {
            this.mergeEtaRatioThreshold = mergeEtaRatioThreshold;
        }
    }

    public static final class MicroCluster {
        private int timeBucketMinutes = 15;
        private double splitScoreThreshold = 0.55;

        public int getTimeBucketMinutes() {
            return timeBucketMinutes;
        }

        public void setTimeBucketMinutes(int timeBucketMinutes) {
            this.timeBucketMinutes = timeBucketMinutes;
        }

        public double getSplitScoreThreshold() {
            return splitScoreThreshold;
        }

        public void setSplitScoreThreshold(double splitScoreThreshold) {
            this.splitScoreThreshold = splitScoreThreshold;
        }
    }

    public static final class BoundaryExpansion {
        private double minSupportScoreThreshold = 0.52;
        private int maxBoundaryOrdersPerCluster = 2;
        private double weatherTightenedSupportThreshold = 0.62;

        public double getMinSupportScoreThreshold() {
            return minSupportScoreThreshold;
        }

        public void setMinSupportScoreThreshold(double minSupportScoreThreshold) {
            this.minSupportScoreThreshold = minSupportScoreThreshold;
        }

        public int getMaxBoundaryOrdersPerCluster() {
            return maxBoundaryOrdersPerCluster;
        }

        public void setMaxBoundaryOrdersPerCluster(int maxBoundaryOrdersPerCluster) {
            this.maxBoundaryOrdersPerCluster = maxBoundaryOrdersPerCluster;
        }

        public double getWeatherTightenedSupportThreshold() {
            return weatherTightenedSupportThreshold;
        }

        public void setWeatherTightenedSupportThreshold(double weatherTightenedSupportThreshold) {
            this.weatherTightenedSupportThreshold = weatherTightenedSupportThreshold;
        }
    }

    public static final class Scenario {
        private double weatherBadEtaMultiplier = 1.18;
        private double trafficBadEtaMultiplier = 1.22;
        private int merchantDelayMinutes = 6;
        private double driverDriftPenalty = 0.08;
        private double pickupQueuePenalty = 0.06;
        private final ScenarioForecast forecast = new ScenarioForecast();

        public double getWeatherBadEtaMultiplier() {
            return weatherBadEtaMultiplier;
        }

        public void setWeatherBadEtaMultiplier(double weatherBadEtaMultiplier) {
            this.weatherBadEtaMultiplier = weatherBadEtaMultiplier;
        }

        public double getTrafficBadEtaMultiplier() {
            return trafficBadEtaMultiplier;
        }

        public void setTrafficBadEtaMultiplier(double trafficBadEtaMultiplier) {
            this.trafficBadEtaMultiplier = trafficBadEtaMultiplier;
        }

        public int getMerchantDelayMinutes() {
            return merchantDelayMinutes;
        }

        public void setMerchantDelayMinutes(int merchantDelayMinutes) {
            this.merchantDelayMinutes = merchantDelayMinutes;
        }

        public double getDriverDriftPenalty() {
            return driverDriftPenalty;
        }

        public void setDriverDriftPenalty(double driverDriftPenalty) {
            this.driverDriftPenalty = driverDriftPenalty;
        }

        public double getPickupQueuePenalty() {
            return pickupQueuePenalty;
        }

        public void setPickupQueuePenalty(double pickupQueuePenalty) {
            this.pickupQueuePenalty = pickupQueuePenalty;
        }

        public ScenarioForecast getForecast() {
            return forecast;
        }
    }

    public static final class ScenarioForecast {
        private double zoneBurstThreshold = 0.58;
        private double demandShiftThreshold = 0.57;
        private double postDropShiftThreshold = 0.55;
        private double confidenceThreshold = 0.55;

        public double getZoneBurstThreshold() {
            return zoneBurstThreshold;
        }

        public void setZoneBurstThreshold(double zoneBurstThreshold) {
            this.zoneBurstThreshold = zoneBurstThreshold;
        }

        public double getDemandShiftThreshold() {
            return demandShiftThreshold;
        }

        public void setDemandShiftThreshold(double demandShiftThreshold) {
            this.demandShiftThreshold = demandShiftThreshold;
        }

        public double getPostDropShiftThreshold() {
            return postDropShiftThreshold;
        }

        public void setPostDropShiftThreshold(double postDropShiftThreshold) {
            this.postDropShiftThreshold = postDropShiftThreshold;
        }

        public double getConfidenceThreshold() {
            return confidenceThreshold;
        }

        public void setConfidenceThreshold(double confidenceThreshold) {
            this.confidenceThreshold = confidenceThreshold;
        }
    }

    public static final class Selector {
        private boolean greedyRepairEnabled = true;
        private int repairPassLimit = 1;
        private double fallbackPenalty = 0.03;
        private final Ortools ortools = new Ortools();

        public boolean isGreedyRepairEnabled() {
            return greedyRepairEnabled;
        }

        public void setGreedyRepairEnabled(boolean greedyRepairEnabled) {
            this.greedyRepairEnabled = greedyRepairEnabled;
        }

        public int getRepairPassLimit() {
            return repairPassLimit;
        }

        public void setRepairPassLimit(int repairPassLimit) {
            this.repairPassLimit = repairPassLimit;
        }

        public double getFallbackPenalty() {
            return fallbackPenalty;
        }

        public void setFallbackPenalty(double fallbackPenalty) {
            this.fallbackPenalty = fallbackPenalty;
        }

        public Ortools getOrtools() {
            return ortools;
        }
    }

    public static final class Ml {
        private String modelManifestPath = "services/models/model-manifest.yaml";
        private final Tabular tabular = new Tabular();
        private final Routefinder routefinder = new Routefinder();
        private final Greedrl greedrl = new Greedrl();
        private final MlForecast forecast = new MlForecast();

        public String getModelManifestPath() {
            return modelManifestPath;
        }

        public void setModelManifestPath(String modelManifestPath) {
            this.modelManifestPath = modelManifestPath;
        }

        public Tabular getTabular() {
            return tabular;
        }

        public Routefinder getRoutefinder() {
            return routefinder;
        }

        public Greedrl getGreedrl() {
            return greedrl;
        }

        public MlForecast getForecast() {
            return forecast;
        }
    }

    public static final class Tabular {
        private boolean enabled = false;
        private String baseUrl = "http://127.0.0.1:8091";
        private Duration connectTimeout = Duration.ofMillis(75);
        private Duration readTimeout = Duration.ofMillis(150);

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public Duration getReadTimeout() {
            return readTimeout;
        }

        public void setReadTimeout(Duration readTimeout) {
            this.readTimeout = readTimeout;
        }
    }

    public static final class Routefinder {
        private boolean enabled = false;
        private String baseUrl = "http://127.0.0.1:8092";
        private Duration connectTimeout = Duration.ofMillis(75);
        private Duration readTimeout = Duration.ofMillis(180);
        private Duration alternativesTimeout = Duration.ofMillis(180);
        private Duration refineTimeout = Duration.ofMillis(150);
        private int maxAlternativesPerDriverCandidate = 2;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public Duration getReadTimeout() {
            return readTimeout;
        }

        public void setReadTimeout(Duration readTimeout) {
            this.readTimeout = readTimeout;
        }

        public Duration getAlternativesTimeout() {
            return alternativesTimeout;
        }

        public void setAlternativesTimeout(Duration alternativesTimeout) {
            this.alternativesTimeout = alternativesTimeout;
        }

        public Duration getRefineTimeout() {
            return refineTimeout;
        }

        public void setRefineTimeout(Duration refineTimeout) {
            this.refineTimeout = refineTimeout;
        }

        public int getMaxAlternativesPerDriverCandidate() {
            return maxAlternativesPerDriverCandidate;
        }

        public void setMaxAlternativesPerDriverCandidate(int maxAlternativesPerDriverCandidate) {
            this.maxAlternativesPerDriverCandidate = maxAlternativesPerDriverCandidate;
        }
    }

    public static final class Greedrl {
        private boolean enabled = false;
        private String baseUrl = "http://127.0.0.1:8093";
        private Duration connectTimeout = Duration.ofMillis(75);
        private Duration readTimeout = Duration.ofMillis(180);
        private Duration bundleTimeout = Duration.ofMillis(180);
        private Duration sequenceTimeout = Duration.ofMillis(150);
        private int maxOrdersPerRequest = 8;
        private int maxProposalsPerCluster = 3;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public Duration getReadTimeout() {
            return readTimeout;
        }

        public void setReadTimeout(Duration readTimeout) {
            this.readTimeout = readTimeout;
        }

        public Duration getBundleTimeout() {
            return bundleTimeout;
        }

        public void setBundleTimeout(Duration bundleTimeout) {
            this.bundleTimeout = bundleTimeout;
        }

        public Duration getSequenceTimeout() {
            return sequenceTimeout;
        }

        public void setSequenceTimeout(Duration sequenceTimeout) {
            this.sequenceTimeout = sequenceTimeout;
        }

        public int getMaxOrdersPerRequest() {
            return maxOrdersPerRequest;
        }

        public void setMaxOrdersPerRequest(int maxOrdersPerRequest) {
            this.maxOrdersPerRequest = maxOrdersPerRequest;
        }

        public int getMaxProposalsPerCluster() {
            return maxProposalsPerCluster;
        }

        public void setMaxProposalsPerCluster(int maxProposalsPerCluster) {
            this.maxProposalsPerCluster = maxProposalsPerCluster;
        }
    }

    public static final class MlForecast {
        private boolean enabled = false;
        private String baseUrl = "http://127.0.0.1:8096";
        private Duration connectTimeout = Duration.ofMillis(75);
        private Duration readTimeout = Duration.ofMillis(180);

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public Duration getReadTimeout() {
            return readTimeout;
        }

        public void setReadTimeout(Duration readTimeout) {
            this.readTimeout = readTimeout;
        }
    }

    public static final class Ortools {
        private Duration timeout = Duration.ofMillis(150);
        private int objectiveScaleFactor = 1_000;

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }

        public int getObjectiveScaleFactor() {
            return objectiveScaleFactor;
        }

        public void setObjectiveScaleFactor(int objectiveScaleFactor) {
            this.objectiveScaleFactor = objectiveScaleFactor;
        }
    }

    public static final class Weather {
        private boolean enabled = false;
        private String baseUrl = "http://127.0.0.1:8094";
        private Duration connectTimeout = Duration.ofMillis(75);
        private Duration readTimeout = Duration.ofMillis(180);
        private double confidenceThreshold = 0.45;
        private boolean staleSignalSuppressionEnabled = true;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public Duration getReadTimeout() {
            return readTimeout;
        }

        public void setReadTimeout(Duration readTimeout) {
            this.readTimeout = readTimeout;
        }

        public double getConfidenceThreshold() {
            return confidenceThreshold;
        }

        public void setConfidenceThreshold(double confidenceThreshold) {
            this.confidenceThreshold = confidenceThreshold;
        }

        public boolean isStaleSignalSuppressionEnabled() {
            return staleSignalSuppressionEnabled;
        }

        public void setStaleSignalSuppressionEnabled(boolean staleSignalSuppressionEnabled) {
            this.staleSignalSuppressionEnabled = staleSignalSuppressionEnabled;
        }
    }

    public static final class Traffic {
        private boolean enabled = false;
        private String baseUrl = "http://127.0.0.1:8095";
        private String apiKey = "";
        private Duration connectTimeout = Duration.ofMillis(75);
        private Duration readTimeout = Duration.ofMillis(180);
        private double confidenceThreshold = 0.5;
        private int refineBudgetPerTick = 8;
        private int maxRefinedLegsPerRequest = 1;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public String getApiKey() {
            return apiKey;
        }

        public void setApiKey(String apiKey) {
            this.apiKey = apiKey;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public Duration getReadTimeout() {
            return readTimeout;
        }

        public void setReadTimeout(Duration readTimeout) {
            this.readTimeout = readTimeout;
        }

        public double getConfidenceThreshold() {
            return confidenceThreshold;
        }

        public void setConfidenceThreshold(double confidenceThreshold) {
            this.confidenceThreshold = confidenceThreshold;
        }

        public int getRefineBudgetPerTick() {
            return refineBudgetPerTick;
        }

        public void setRefineBudgetPerTick(int refineBudgetPerTick) {
            this.refineBudgetPerTick = refineBudgetPerTick;
        }

        public int getMaxRefinedLegsPerRequest() {
            return maxRefinedLegsPerRequest;
        }

        public void setMaxRefinedLegsPerRequest(int maxRefinedLegsPerRequest) {
            this.maxRefinedLegsPerRequest = maxRefinedLegsPerRequest;
        }
    }

    public static final class Feedback {
        private boolean decisionLogEnabled = true;
        private boolean snapshotEnabled = true;
        private boolean replayEnabled = true;
        private FeedbackStorageMode storageMode = FeedbackStorageMode.IN_MEMORY;
        private String baseDir = "build/dispatch-v2-feedback";
        private final Retention retention = new Retention();

        public boolean isDecisionLogEnabled() {
            return decisionLogEnabled;
        }

        public void setDecisionLogEnabled(boolean decisionLogEnabled) {
            this.decisionLogEnabled = decisionLogEnabled;
        }

        public boolean isSnapshotEnabled() {
            return snapshotEnabled;
        }

        public void setSnapshotEnabled(boolean snapshotEnabled) {
            this.snapshotEnabled = snapshotEnabled;
        }

        public boolean isReplayEnabled() {
            return replayEnabled;
        }

        public void setReplayEnabled(boolean replayEnabled) {
            this.replayEnabled = replayEnabled;
        }

        public FeedbackStorageMode getStorageMode() {
            return storageMode;
        }

        public void setStorageMode(FeedbackStorageMode storageMode) {
            this.storageMode = storageMode;
        }

        public String getBaseDir() {
            return baseDir;
        }

        public void setBaseDir(String baseDir) {
            this.baseDir = baseDir;
        }

        public Retention getRetention() {
            return retention;
        }
    }

    public static final class Retention {
        private int maxFiles = 20;

        public int getMaxFiles() {
            return maxFiles;
        }

        public void setMaxFiles(int maxFiles) {
            this.maxFiles = maxFiles;
        }
    }

    public static final class Harvest {
        private boolean enabled = true;
        private String baseDir = "data/bronze";
        private int queueCapacity = 4_096;
        private Duration flushInterval = Duration.ofMillis(250);
        private long maxFileSizeBytes = 8L * 1024L * 1024L;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getBaseDir() {
            return baseDir;
        }

        public void setBaseDir(String baseDir) {
            this.baseDir = baseDir;
        }

        public int getQueueCapacity() {
            return queueCapacity;
        }

        public void setQueueCapacity(int queueCapacity) {
            this.queueCapacity = queueCapacity;
        }

        public Duration getFlushInterval() {
            return flushInterval;
        }

        public void setFlushInterval(Duration flushInterval) {
            this.flushInterval = flushInterval;
        }

        public long getMaxFileSizeBytes() {
            return maxFileSizeBytes;
        }

        public void setMaxFileSizeBytes(long maxFileSizeBytes) {
            this.maxFileSizeBytes = maxFileSizeBytes;
        }
    }

    public static final class WarmHotStart {
        private boolean loadLatestSnapshotOnBoot = true;

        public boolean isLoadLatestSnapshotOnBoot() {
            return loadLatestSnapshotOnBoot;
        }

        public void setLoadLatestSnapshotOnBoot(boolean loadLatestSnapshotOnBoot) {
            this.loadLatestSnapshotOnBoot = loadLatestSnapshotOnBoot;
        }
    }

    public static final class Performance {
        private boolean telemetryEnabled = true;
        private boolean budgetEnforcementEnabled = false;
        private Duration totalDispatchBudget = Duration.ofMillis(1200);
        private Map<String, Duration> stageBudgets = defaultStageBudgets();

        public boolean isTelemetryEnabled() {
            return telemetryEnabled;
        }

        public void setTelemetryEnabled(boolean telemetryEnabled) {
            this.telemetryEnabled = telemetryEnabled;
        }

        public boolean isBudgetEnforcementEnabled() {
            return budgetEnforcementEnabled;
        }

        public void setBudgetEnforcementEnabled(boolean budgetEnforcementEnabled) {
            this.budgetEnforcementEnabled = budgetEnforcementEnabled;
        }

        public Duration getTotalDispatchBudget() {
            return totalDispatchBudget;
        }

        public void setTotalDispatchBudget(Duration totalDispatchBudget) {
            this.totalDispatchBudget = totalDispatchBudget;
        }

        public Map<String, Duration> getStageBudgets() {
            return stageBudgets;
        }

        public void setStageBudgets(Map<String, Duration> stageBudgets) {
            this.stageBudgets = stageBudgets == null ? defaultStageBudgets() : new LinkedHashMap<>(stageBudgets);
        }

        private static Map<String, Duration> defaultStageBudgets() {
            LinkedHashMap<String, Duration> budgets = new LinkedHashMap<>();
            budgets.put("eta/context", Duration.ofMillis(300));
            budgets.put("order-buffer", Duration.ofMillis(15));
            budgets.put("pair-graph", Duration.ofMillis(180));
            budgets.put("micro-cluster", Duration.ofMillis(25));
            budgets.put("boundary-expansion", Duration.ofMillis(40));
            budgets.put("bundle-pool", Duration.ofMillis(240));
            budgets.put("pickup-anchor", Duration.ofMillis(20));
            budgets.put("driver-shortlist/rerank", Duration.ofMillis(180));
            budgets.put("route-proposal-pool", Duration.ofMillis(320));
            budgets.put("scenario-evaluation", Duration.ofMillis(220));
            budgets.put("global-selector", Duration.ofMillis(180));
            budgets.put("dispatch-executor", Duration.ofMillis(40));
            return budgets;
        }
    }

    public static final class Compute {
        private final Adaptive adaptive = new Adaptive();

        public Adaptive getAdaptive() {
            return adaptive;
        }
    }

    public static final class Adaptive {
        private boolean enabled = false;
        private String profileName = "dispatch-v2-full-adaptive";
        private String machineProfile = "local";
        private boolean requireWorkerDeviceAudit = true;
        private boolean failOpenWhenWorkerMetadataMissing = false;
        private int routefinderMaxTuplesPerDispatch = 4;
        private double routefinderEtaAmbiguityThresholdMinutes = 1.5;
        private int routefinderStopCountThreshold = 3;
        private boolean routefinderWeatherEscalationEnabled = true;
        private boolean routefinderTrafficEscalationEnabled = true;
        private boolean routefinderBoundaryCrossEscalationEnabled = true;
        private int greedrlMinWorkingOrders = 4;
        private int greedrlMinAcceptedBoundaryOrders = 1;
        private double greedrlSupportSpreadThreshold = 0.12;
        private boolean forecastEnabledInHotPathByDefault = false;
        private double forecastAmbiguityThresholdMinutes = 1.8;
        private int forecastMinProposalCount = 2;
        private boolean forecastWeatherEscalationEnabled = true;
        private boolean forecastTrafficEscalationEnabled = true;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getProfileName() {
            return profileName;
        }

        public void setProfileName(String profileName) {
            this.profileName = profileName;
        }

        public String getMachineProfile() {
            return machineProfile;
        }

        public void setMachineProfile(String machineProfile) {
            this.machineProfile = machineProfile;
        }

        public boolean isRequireWorkerDeviceAudit() {
            return requireWorkerDeviceAudit;
        }

        public void setRequireWorkerDeviceAudit(boolean requireWorkerDeviceAudit) {
            this.requireWorkerDeviceAudit = requireWorkerDeviceAudit;
        }

        public boolean isFailOpenWhenWorkerMetadataMissing() {
            return failOpenWhenWorkerMetadataMissing;
        }

        public void setFailOpenWhenWorkerMetadataMissing(boolean failOpenWhenWorkerMetadataMissing) {
            this.failOpenWhenWorkerMetadataMissing = failOpenWhenWorkerMetadataMissing;
        }

        public int getRoutefinderMaxTuplesPerDispatch() {
            return routefinderMaxTuplesPerDispatch;
        }

        public void setRoutefinderMaxTuplesPerDispatch(int routefinderMaxTuplesPerDispatch) {
            this.routefinderMaxTuplesPerDispatch = routefinderMaxTuplesPerDispatch;
        }

        public double getRoutefinderEtaAmbiguityThresholdMinutes() {
            return routefinderEtaAmbiguityThresholdMinutes;
        }

        public void setRoutefinderEtaAmbiguityThresholdMinutes(double routefinderEtaAmbiguityThresholdMinutes) {
            this.routefinderEtaAmbiguityThresholdMinutes = routefinderEtaAmbiguityThresholdMinutes;
        }

        public int getRoutefinderStopCountThreshold() {
            return routefinderStopCountThreshold;
        }

        public void setRoutefinderStopCountThreshold(int routefinderStopCountThreshold) {
            this.routefinderStopCountThreshold = routefinderStopCountThreshold;
        }

        public boolean isRoutefinderWeatherEscalationEnabled() {
            return routefinderWeatherEscalationEnabled;
        }

        public void setRoutefinderWeatherEscalationEnabled(boolean routefinderWeatherEscalationEnabled) {
            this.routefinderWeatherEscalationEnabled = routefinderWeatherEscalationEnabled;
        }

        public boolean isRoutefinderTrafficEscalationEnabled() {
            return routefinderTrafficEscalationEnabled;
        }

        public void setRoutefinderTrafficEscalationEnabled(boolean routefinderTrafficEscalationEnabled) {
            this.routefinderTrafficEscalationEnabled = routefinderTrafficEscalationEnabled;
        }

        public boolean isRoutefinderBoundaryCrossEscalationEnabled() {
            return routefinderBoundaryCrossEscalationEnabled;
        }

        public void setRoutefinderBoundaryCrossEscalationEnabled(boolean routefinderBoundaryCrossEscalationEnabled) {
            this.routefinderBoundaryCrossEscalationEnabled = routefinderBoundaryCrossEscalationEnabled;
        }

        public int getGreedrlMinWorkingOrders() {
            return greedrlMinWorkingOrders;
        }

        public void setGreedrlMinWorkingOrders(int greedrlMinWorkingOrders) {
            this.greedrlMinWorkingOrders = greedrlMinWorkingOrders;
        }

        public int getGreedrlMinAcceptedBoundaryOrders() {
            return greedrlMinAcceptedBoundaryOrders;
        }

        public void setGreedrlMinAcceptedBoundaryOrders(int greedrlMinAcceptedBoundaryOrders) {
            this.greedrlMinAcceptedBoundaryOrders = greedrlMinAcceptedBoundaryOrders;
        }

        public double getGreedrlSupportSpreadThreshold() {
            return greedrlSupportSpreadThreshold;
        }

        public void setGreedrlSupportSpreadThreshold(double greedrlSupportSpreadThreshold) {
            this.greedrlSupportSpreadThreshold = greedrlSupportSpreadThreshold;
        }

        public boolean isForecastEnabledInHotPathByDefault() {
            return forecastEnabledInHotPathByDefault;
        }

        public void setForecastEnabledInHotPathByDefault(boolean forecastEnabledInHotPathByDefault) {
            this.forecastEnabledInHotPathByDefault = forecastEnabledInHotPathByDefault;
        }

        public double getForecastAmbiguityThresholdMinutes() {
            return forecastAmbiguityThresholdMinutes;
        }

        public void setForecastAmbiguityThresholdMinutes(double forecastAmbiguityThresholdMinutes) {
            this.forecastAmbiguityThresholdMinutes = forecastAmbiguityThresholdMinutes;
        }

        public int getForecastMinProposalCount() {
            return forecastMinProposalCount;
        }

        public void setForecastMinProposalCount(int forecastMinProposalCount) {
            this.forecastMinProposalCount = forecastMinProposalCount;
        }

        public boolean isForecastWeatherEscalationEnabled() {
            return forecastWeatherEscalationEnabled;
        }

        public void setForecastWeatherEscalationEnabled(boolean forecastWeatherEscalationEnabled) {
            this.forecastWeatherEscalationEnabled = forecastWeatherEscalationEnabled;
        }

        public boolean isForecastTrafficEscalationEnabled() {
            return forecastTrafficEscalationEnabled;
        }

        public void setForecastTrafficEscalationEnabled(boolean forecastTrafficEscalationEnabled) {
            this.forecastTrafficEscalationEnabled = forecastTrafficEscalationEnabled;
        }
    }

    public static final class Decision {
        private String mode = "llm";
        private boolean fallbackToLegacy = true;
        private java.util.List<String> authoritativeStages = new java.util.ArrayList<>(java.util.List.of(
                "pair-bundle",
                "driver",
                "route-critique",
                "scenario",
                "final-selection"));
        private final EffortPolicy effortPolicy = new EffortPolicy();
        private final ContextSelection contextSelection = new ContextSelection();
        private final Llm llm = new Llm();

        public String getMode() {
            return mode;
        }

        public void setMode(String mode) {
            this.mode = mode;
        }

        public boolean isFallbackToLegacy() {
            return fallbackToLegacy;
        }

        public void setFallbackToLegacy(boolean fallbackToLegacy) {
            this.fallbackToLegacy = fallbackToLegacy;
        }

        public java.util.List<String> getAuthoritativeStages() {
            return authoritativeStages;
        }

        public void setAuthoritativeStages(java.util.List<String> authoritativeStages) {
            this.authoritativeStages = authoritativeStages == null
                    ? new java.util.ArrayList<>()
                    : new java.util.ArrayList<>(authoritativeStages);
        }

        public Llm getLlm() {
            return llm;
        }

        public EffortPolicy getEffortPolicy() {
            return effortPolicy;
        }

        public ContextSelection getContextSelection() {
            return contextSelection;
        }
    }

    public static final class EffortPolicy {
        private boolean dynamicEnabled = true;
        private int lowComplexityThreshold = 3;
        private int highComplexityThreshold = 8;
        private Duration latencyPressureThreshold = Duration.ofMillis(900);

        public boolean isDynamicEnabled() {
            return dynamicEnabled;
        }

        public void setDynamicEnabled(boolean dynamicEnabled) {
            this.dynamicEnabled = dynamicEnabled;
        }

        public int getLowComplexityThreshold() {
            return lowComplexityThreshold;
        }

        public void setLowComplexityThreshold(int lowComplexityThreshold) {
            this.lowComplexityThreshold = lowComplexityThreshold;
        }

        public int getHighComplexityThreshold() {
            return highComplexityThreshold;
        }

        public void setHighComplexityThreshold(int highComplexityThreshold) {
            this.highComplexityThreshold = highComplexityThreshold;
        }

        public Duration getLatencyPressureThreshold() {
            return latencyPressureThreshold;
        }

        public void setLatencyPressureThreshold(Duration latencyPressureThreshold) {
            this.latencyPressureThreshold = latencyPressureThreshold;
        }
    }

    public static final class ContextSelection {
        private boolean dynamicEnabled = true;
        private boolean toolFetchEnabled = true;
        private int compactCandidateThreshold = 3;
        private int denseCandidateThreshold = 8;

        public boolean isDynamicEnabled() {
            return dynamicEnabled;
        }

        public void setDynamicEnabled(boolean dynamicEnabled) {
            this.dynamicEnabled = dynamicEnabled;
        }

        public boolean isToolFetchEnabled() {
            return toolFetchEnabled;
        }

        public void setToolFetchEnabled(boolean toolFetchEnabled) {
            this.toolFetchEnabled = toolFetchEnabled;
        }

        public int getCompactCandidateThreshold() {
            return compactCandidateThreshold;
        }

        public void setCompactCandidateThreshold(int compactCandidateThreshold) {
            this.compactCandidateThreshold = compactCandidateThreshold;
        }

        public int getDenseCandidateThreshold() {
            return denseCandidateThreshold;
        }

        public void setDenseCandidateThreshold(int denseCandidateThreshold) {
            this.denseCandidateThreshold = denseCandidateThreshold;
        }
    }

    public static final class Llm {
        private String provider = "9router";
        private String baseUrl = "http://127.0.0.1:20128/v1";
        private String wireApi = "responses";
        private String model = "cx/gpt-5.5";
        private String promptFamily = "v2";
        private String apiKeyEnv = "OPENAI_API_KEY";
        private Duration timeoutMs = Duration.ofSeconds(20);
        private int maxRetries = 0;
        private int modelDiscoveryRetryCount = 1;
        private boolean modelDiscoveryRequired = false;
        private Duration modelDiscoveryCacheTtl = Duration.ofMinutes(10);
        private java.util.List<String> fallbackModels = new java.util.ArrayList<>(java.util.List.of("cx/gpt-5.4"));
        private boolean parallelToolCalls = false;
        private boolean strictStructuredOutputs = true;
        private boolean multiPassEnabled = true;
        private boolean skillRegistryEnabled = true;
        private java.util.Map<String, Integer> maxPassesByStage = new java.util.LinkedHashMap<>(java.util.Map.of(
                "route-critique", 1,
                "final-selection", 1));
        private java.util.Map<String, String> effortOverridesByStage = new java.util.LinkedHashMap<>(java.util.Map.of(
                "route-critique", "low",
                "final-selection", "low"));
        private java.util.Map<String, Integer> maxInputTokensByStage = new java.util.LinkedHashMap<>(java.util.Map.of(
                "route-critique", 24000,
                "final-selection", 14000));
        private java.util.List<String> forceCompactStages = new java.util.ArrayList<>(java.util.List.of(
                "route-critique",
                "final-selection"));
        private double authorityMinSelectionRetainRatio = 0.75;
        private java.util.List<String> authorityHardRiskReasonCodes = new java.util.ArrayList<>(java.util.List.of(
                "conflict-risk",
                "hard-constraint-risk",
                "route-invalid-risk"));
        private java.util.List<String> multiPassStages = new java.util.ArrayList<>(java.util.List.of(
                "driver",
                "route-generation",
                "route-critique",
                "scenario",
                "final-selection"));
        private final SessionStore sessionStore = new SessionStore();

        public String getProvider() {
            return provider;
        }

        public void setProvider(String provider) {
            this.provider = provider;
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public String getWireApi() {
            return wireApi;
        }

        public void setWireApi(String wireApi) {
            this.wireApi = wireApi;
        }

        public String getModel() {
            return model;
        }

        public void setModel(String model) {
            this.model = model;
        }

        public String getPromptFamily() {
            return promptFamily;
        }

        public void setPromptFamily(String promptFamily) {
            this.promptFamily = promptFamily;
        }

        public String getApiKeyEnv() {
            return apiKeyEnv;
        }

        public void setApiKeyEnv(String apiKeyEnv) {
            this.apiKeyEnv = apiKeyEnv;
        }

        public Duration getTimeoutMs() {
            return timeoutMs;
        }

        public void setTimeoutMs(Duration timeoutMs) {
            this.timeoutMs = timeoutMs;
        }

        public int getMaxRetries() {
            return maxRetries;
        }

        public void setMaxRetries(int maxRetries) {
            this.maxRetries = maxRetries;
        }

        public int getModelDiscoveryRetryCount() {
            return modelDiscoveryRetryCount;
        }

        public void setModelDiscoveryRetryCount(int modelDiscoveryRetryCount) {
            this.modelDiscoveryRetryCount = modelDiscoveryRetryCount;
        }

        public boolean isModelDiscoveryRequired() {
            return modelDiscoveryRequired;
        }

        public void setModelDiscoveryRequired(boolean modelDiscoveryRequired) {
            this.modelDiscoveryRequired = modelDiscoveryRequired;
        }

        public Duration getModelDiscoveryCacheTtl() {
            return modelDiscoveryCacheTtl;
        }

        public void setModelDiscoveryCacheTtl(Duration modelDiscoveryCacheTtl) {
            this.modelDiscoveryCacheTtl = modelDiscoveryCacheTtl;
        }

        public java.util.List<String> getFallbackModels() {
            return fallbackModels;
        }

        public void setFallbackModels(java.util.List<String> fallbackModels) {
            this.fallbackModels = fallbackModels == null
                    ? new java.util.ArrayList<>()
                    : new java.util.ArrayList<>(fallbackModels);
        }

        public boolean isParallelToolCalls() {
            return parallelToolCalls;
        }

        public void setParallelToolCalls(boolean parallelToolCalls) {
            this.parallelToolCalls = parallelToolCalls;
        }

        public boolean isStrictStructuredOutputs() {
            return strictStructuredOutputs;
        }

        public void setStrictStructuredOutputs(boolean strictStructuredOutputs) {
            this.strictStructuredOutputs = strictStructuredOutputs;
        }

        public boolean isMultiPassEnabled() {
            return multiPassEnabled;
        }

        public void setMultiPassEnabled(boolean multiPassEnabled) {
            this.multiPassEnabled = multiPassEnabled;
        }

        public boolean isSkillRegistryEnabled() {
            return skillRegistryEnabled;
        }

        public void setSkillRegistryEnabled(boolean skillRegistryEnabled) {
            this.skillRegistryEnabled = skillRegistryEnabled;
        }

        public java.util.Map<String, Integer> getMaxPassesByStage() {
            return maxPassesByStage;
        }

        public void setMaxPassesByStage(java.util.Map<String, Integer> maxPassesByStage) {
            this.maxPassesByStage = maxPassesByStage == null
                    ? new java.util.LinkedHashMap<>()
                    : new java.util.LinkedHashMap<>(maxPassesByStage);
        }

        public java.util.Map<String, String> getEffortOverridesByStage() {
            return effortOverridesByStage;
        }

        public void setEffortOverridesByStage(java.util.Map<String, String> effortOverridesByStage) {
            this.effortOverridesByStage = effortOverridesByStage == null
                    ? new java.util.LinkedHashMap<>()
                    : new java.util.LinkedHashMap<>(effortOverridesByStage);
        }

        public java.util.Map<String, Integer> getMaxInputTokensByStage() {
            return maxInputTokensByStage;
        }

        public void setMaxInputTokensByStage(java.util.Map<String, Integer> maxInputTokensByStage) {
            this.maxInputTokensByStage = maxInputTokensByStage == null
                    ? new java.util.LinkedHashMap<>()
                    : new java.util.LinkedHashMap<>(maxInputTokensByStage);
        }

        public java.util.List<String> getForceCompactStages() {
            return forceCompactStages;
        }

        public void setForceCompactStages(java.util.List<String> forceCompactStages) {
            this.forceCompactStages = forceCompactStages == null
                    ? new java.util.ArrayList<>()
                    : new java.util.ArrayList<>(forceCompactStages);
        }

        public double getAuthorityMinSelectionRetainRatio() {
            return authorityMinSelectionRetainRatio;
        }

        public void setAuthorityMinSelectionRetainRatio(double authorityMinSelectionRetainRatio) {
            this.authorityMinSelectionRetainRatio = authorityMinSelectionRetainRatio;
        }

        public java.util.List<String> getAuthorityHardRiskReasonCodes() {
            return authorityHardRiskReasonCodes;
        }

        public void setAuthorityHardRiskReasonCodes(java.util.List<String> authorityHardRiskReasonCodes) {
            this.authorityHardRiskReasonCodes = authorityHardRiskReasonCodes == null
                    ? new java.util.ArrayList<>()
                    : new java.util.ArrayList<>(authorityHardRiskReasonCodes);
        }

        public java.util.List<String> getMultiPassStages() {
            return multiPassStages;
        }

        public void setMultiPassStages(java.util.List<String> multiPassStages) {
            this.multiPassStages = multiPassStages == null
                    ? new java.util.ArrayList<>()
                    : new java.util.ArrayList<>(multiPassStages);
        }

        public SessionStore getSessionStore() {
            return sessionStore;
        }
    }

    public static final class SessionStore {
        private boolean enabled = true;
        private String baseDir = "build/dispatch-v2-feedback/decision-session-store";
        private Duration ttl = Duration.ofMinutes(10);

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getBaseDir() {
            return baseDir;
        }

        public void setBaseDir(String baseDir) {
            this.baseDir = baseDir;
        }

        public Duration getTtl() {
            return ttl;
        }

        public void setTtl(Duration ttl) {
            this.ttl = ttl;
        }
    }
}
