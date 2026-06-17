document.addEventListener("alpine:init", () => {
  Alpine.data("approvalsPage", () => ({
    items: [],
    loading: false,
    error: "",
    comment: "",

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

    init() {
      if (!guardPage(["manager"])) return;
      this.loadApprovals();
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
