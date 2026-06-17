document.addEventListener("alpine:init", () => {
  Alpine.data("schedulePage", () => ({
    items: [],
    employees: [],
    selectedDate: localTodayISO(),
    employeeName: "",
    loading: false,
    completingId: null,
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

    buildingLabel(value) {
      return buildingLabel(value);
    },

    managerCommentLabel(status) {
      return managerCommentLabel(status);
    },

    statusLabel(status) {
      return TICKET_STATUS_LABELS[status] || status || "—";
    },

    async completeTicket(item) {
      if (!item?.id || !item.can_complete) return;
      if (!confirm("Отметить заявку как выполненную?")) return;

      this.completingId = item.id;
      this.error = "";
      try {
        const updated = await apiRequest(`/schedule/${item.id}/complete`, "POST");
        const index = this.items.findIndex((row) => row.id === item.id);
        if (index >= 0) {
          this.items[index] = updated;
        }
        if (this.detailsItem?.id === item.id) {
          this.detailsItem = updated;
        }
        showToast("Заявка отмечена как выполненная", "success");
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.completingId = null;
      }
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
