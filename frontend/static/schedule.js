document.addEventListener("alpine:init", () => {
  Alpine.data("schedulePage", () => ({
    items: [],
    employeeId: "",
    loading: false,
    error: "",
    refreshTimer: null,

    async loadSchedule() {
      this.loading = true;
      this.error = "";
      try {
        const query = this.employeeId ? `?employee_id=${encodeURIComponent(this.employeeId)}` : "";
        this.items = await apiRequest(`/schedule/current${query}`);
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },

    init() {
      if (!guardPage(["employee", "manager"])) return;
      this.loadSchedule();
      this.refreshTimer = setInterval(() => this.loadSchedule(), 30000);
    },

    destroy() {
      if (this.refreshTimer) clearInterval(this.refreshTimer);
    },
  }));
});
