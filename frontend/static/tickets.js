document.addEventListener("alpine:init", () => {
  Alpine.data("ticketPage", () => ({
    rawText: "",
    ticketId: null,
    status: "",
    missingFields: [],
    questions: [],
    answers: {},
    extracted: {},
    loading: false,
    error: "",

    get isClarification() {
      return this.status === "need_clarification";
    },

    get isReady() {
      return this.status === "ready_for_scheduling";
    },

    fieldLabel(field) {
      return FIELD_LABELS[field] || field;
    },

    ticketTypeLabel(value) {
      return TICKET_TYPE_LABELS[value] || value || "—";
    },

    priorityLabel(value) {
      return PRIORITY_LABELS[value] || value || "—";
    },

    resetAnswers() {
      this.answers = {};
      this.missingFields.forEach((field) => {
        this.answers[field] = "";
      });
    },

    applyTicketResponse(data) {
      this.ticketId = data.id;
      this.status = data.status;
      this.missingFields = data.missing_fields || [];
      this.questions = data.questions || [];
      this.extracted = {
        location: data.extracted_location,
        problem_description: data.extracted_problem,
        ticket_type: data.ticket_type,
        priority: data.priority,
        estimated_minutes: data.estimated_minutes,
        required_skill: data.required_skill,
      };
      this.resetAnswers();
    },

    applyClarificationResponse(data) {
      this.status = data.status;
      this.missingFields = data.missing_fields || [];
      this.questions = data.questions || [];
      this.extracted = data.extracted || {};
      this.resetAnswers();
    },

    async submitTicket() {
      this.error = "";
      if (!this.rawText.trim()) {
        this.error = "Введите текст заявки";
        return;
      }

      this.loading = true;
      try {
        const data = await apiRequest("/tickets/", "POST", { raw_text: this.rawText.trim() });
        this.applyTicketResponse(data);
        showToast("Заявка отправлена", "success");
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },

    async submitAnswers() {
      this.error = "";
      if (!this.ticketId) {
        this.error = "Сначала отправьте заявку";
        return;
      }

      const payload = {};
      this.missingFields.forEach((field) => {
        const value = this.answers[field];
        if (value !== undefined && value !== null && String(value).trim() !== "") {
          payload[field] = value;
        }
      });

      if (!Object.keys(payload).length) {
        this.error = "Заполните хотя бы одно поле для уточнения";
        return;
      }

      this.loading = true;
      try {
        const data = await apiRequest(`/tickets/${this.ticketId}/clarify`, "POST", {
          answers: payload,
        });
        this.applyClarificationResponse(data);
        showToast(
          data.status === "ready_for_scheduling"
            ? "Заявка готова к планированию"
            : "Ответ принят, требуется дополнительное уточнение",
          "success"
        );
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },
  }));
});
