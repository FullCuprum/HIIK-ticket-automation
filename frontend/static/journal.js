document.addEventListener("alpine:init", () => {
  Alpine.data("journalPage", () => ({
    items: [],
    authors: [],
    dateFrom: localDaysAgoISO(30),
    dateTo: localTodayISO(),
    creatorUsername: "",
    loading: false,
    error: "",
    showDetails: false,
    detailsItem: null,

    get isAdmin() {
      const role = getRole();
      return role === "admin" || role === "manager";
    },

    get emptyMessage() {
      return `За период с ${formatDisplayDate(this.dateFrom)} по ${formatDisplayDate(this.dateTo)} заявок не найдено.`;
    },

    statusLabel(status) {
      return TICKET_STATUS_LABELS[status] || status;
    },

    ticketTypeLabel(value) {
      return TICKET_TYPE_LABELS[value] || value || "—";
    },

    priorityLabel(value) {
      return PRIORITY_LABELS[value] || value || "—";
    },

    descriptionPreview(item) {
      return item.extracted_problem || item.raw_text || "—";
    },

    buildQuery() {
      const params = new URLSearchParams();
      if (this.dateFrom) params.set("date_from", this.dateFrom);
      if (this.dateTo) params.set("date_to", this.dateTo);
      if (this.isAdmin && this.creatorUsername) {
        params.set("creator_username", this.creatorUsername);
      }
      const query = params.toString();
      return query ? `?${query}` : "";
    },

    openDetails(item) {
      this.detailsItem = item;
      this.showDetails = true;
    },

    async loadAuthors() {
      if (!this.isAdmin) return;
      try {
        this.authors = await apiRequest("/tickets/journal/authors");
      } catch (error) {
        showToast(error.message, "error");
      }
    },

    async loadJournal() {
      this.loading = true;
      this.error = "";
      try {
        this.items = await apiRequest(`/tickets/journal${this.buildQuery()}`);
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },

    async init() {
      if (!guardPage(["user", "employee", "admin", "manager"])) return;
      await this.loadAuthors();
      await this.loadJournal();
    },
  }));
});
