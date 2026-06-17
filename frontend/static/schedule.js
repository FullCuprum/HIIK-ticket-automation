document.addEventListener("alpine:init", () => {
  Alpine.data("schedulePage", () => ({
    items: [],
    employees: [],
    selectedDate: localTodayISO(),
    employeeName: "",
    loading: false,
    error: "",
    refreshTimer: null,
    showDetails: false,
    detailsItem: null,

    get pageTitle() {
      const label = formatDisplayDate(this.selectedDate);
      return this.selectedDate === localTodayISO()
        ? `Расписание на сегодня (${label})`
        : `Расписание на ${label}`;
    },

    get emptyMessage() {
      return `На ${formatDisplayDate(this.selectedDate)} задач в расписании нет.`;
    },

    buildQuery() {
      const params = new URLSearchParams();
      if (this.selectedDate) {
        params.set("schedule_date", this.selectedDate);
      }
      if (this.employeeName) {
        params.set("employee_name", this.employeeName);
      }
      const query = params.toString();
      return query ? `?${query}` : "";
    },

    openDetails(item) {
      this.detailsItem = item;
      this.showDetails = true;
    },

    async loadEmployees() {
      try {
        this.employees = await apiRequest("/schedule/employees");
      } catch (error) {
        showToast(error.message, "error");
      }
    },

    async loadSchedule() {
      this.loading = true;
      this.error = "";
      try {
        this.items = await apiRequest(`/schedule/current${this.buildQuery()}`);
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },

    async init() {
      if (!guardPage(["employee", "admin", "manager"])) return;
      await this.loadEmployees();
      await this.loadSchedule();
      this.refreshTimer = setInterval(() => this.loadSchedule(), 30000);
    },

    destroy() {
      if (this.refreshTimer) clearInterval(this.refreshTimer);
    },
  }));
});
