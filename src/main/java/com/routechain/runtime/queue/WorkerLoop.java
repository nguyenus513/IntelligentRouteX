package com.routechain.runtime.queue;

public final class WorkerLoop {
    private final QueueLane lane;
    private boolean busy;
    public WorkerLoop(QueueLane lane) { this.lane = lane; }
    public QueueLane lane() { return lane; }
    public boolean busy() { return busy; }
    public void markBusy(boolean busy) { this.busy = busy; }
}
