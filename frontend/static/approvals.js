document.addEventListener("alpine:init", () => {
  Alpine.data("approvalsPage", () => ({
    items: [],
    employees: [],
    buildingOptions: Object.entries(BUILDING_LABELS).map(([value, label]) => ({ value, label })),
    loading: false,
    saving: false,
    error: "",
    comment: "",
    showDetails: false,
    showEditForm: false,
    detailsItem: null,
    editForm: {
      id: null,
      description: "",
      location: "",
      building: "",
      employee_id: "",
      start_time_local: "",
      end_time_local: "",
    },

    async loadApprovals() {
      this.loading = true;
      this.error = "";
      try {
        this.items = await apiRequest("/schedule/approvals");
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },

    async loadEmployees() {
      try {
        this.employees = await apiRequest("/schedule/employees");
      } catch (error) {
        showToast(error.message, "error");
      }
    },

    init() {
      if (!guardPage(["admin", "manager"])) return;
      this.loadEmployees();
      this.loadApprovals();
    },

    openDetails(item) {
      this.detailsItem = item;
      this.showDetails = true;
    },

    openEditForm(item) {
      this.editForm = {
        id: item.id,
        description: item.description || "",
        location: item.location || "",
        building: item.building || "",
        employee_id: String(item.employee_id),
        start_time_local: toDatetimeLocalValue(item.start_time),
        end_time_local: toDatetimeLocalValue(item.end_time),
      };
      this.showEditForm = true;
    },

    async saveProposal() {
      this.saving = true;
      this.error = "";
      try {
        const payload = {
          description: this.editForm.description,
          location: this.editForm.location,
          building: this.editForm.building || null,
          employee_id: Number(this.editForm.employee_id),
          start_time: fromDatetimeLocalValue(this.editForm.start_time_local),
          end_time: fromDatetimeLocalValue(this.editForm.end_time_local),
        };
        await apiRequest(`/schedule/approvals/${this.editForm.id}`, "PUT", payload);
        showToast("Предложение обновлено", "success");
        this.showEditForm = false;
        await this.loadApprovals();
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.saving = false;
      }
    },

    async approveItem(id) {
      await this.processItem(id, "approve");
    },

    async rejectItem(id) {
      await this.processItem(id, "reject");
    },

    async processItem(id, action) {
      this.loading = true;
      this.error = "";
      try {
        await apiRequest(`/schedule/approvals/${id}/${action}`, "POST", {
          manager_comment: this.comment || null,
        });
        showToast(action === "approve" ? "Предложение утверждено" : "Предложение отклонено", "success");
        this.comment = "";
        await this.loadApprovals();
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },
  }));
});
