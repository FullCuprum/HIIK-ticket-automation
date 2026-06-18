document.addEventListener("alpine:init", () => {
  Alpine.data("ticketPage", () => ({
    rawText: "",
    ticketId: null,
    status: "",
    missingFields: [],
    questions: [],
    answers: {},
    extracted: {},
    previewActive: false,
    previewExtracted: {},
    previewMissingFields: [],
    previewQuestions: [],
    previewAnswers: {},
    buildingOptions: Object.entries(BUILDING_LABELS).map(([value, label]) => ({ value, label })),
    ticketTypeOptions: Object.entries(TICKET_TYPE_LABELS).map(([value, label]) => ({ value, label })),
    priorityOptions: Object.entries(PRIORITY_LABELS).map(([value, label]) => ({ value, label })),
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

    buildingLabel(value) {
      return buildingLabel(value);
    },

    ticketTypeLabel(value) {
      return TICKET_TYPE_LABELS[value] || value || "—";
    },

    priorityLabel(value) {
      return PRIORITY_LABELS[value] || value || "—";
    },

    resetPreviewAnswers() {
      this.previewAnswers = {};
      this.previewMissingFields.forEach((field) => {
        this.previewAnswers[field] = "";
      });
    },

    applyPreviewResponse(data) {
      this.previewActive = true;
      this.previewExtracted = data.extracted || {};
      this.previewMissingFields = data.missing_fields || [];
      this.previewQuestions = data.questions || [];
      this.resetPreviewAnswers();
      this.error = "";
    },

    resetPreview() {
      this.previewActive = false;
      this.previewExtracted = {};
      this.previewMissingFields = [];
      this.previewQuestions = [];
      this.previewAnswers = {};
      this.error = "";
    },

    applyTicketResponse(data) {
      this.previewActive = false;
      this.previewExtracted = {};
      this.previewMissingFields = [];
      this.previewQuestions = [];
      this.previewAnswers = {};
      this.ticketId = data.id;
      this.status = data.status;
      this.missingFields = data.missing_fields || [];
      this.questions = data.questions || [];
      this.extracted = {
        building: data.extracted_building,
        location: data.extracted_location,
        problem_description: data.extracted_problem,
        ticket_type: data.ticket_type,
        priority: data.priority,
        estimated_minutes: data.estimated_minutes,
        required_skill: data.required_skill,
        event_datetime: data.event_datetime,
      };
    },

    buildAnswersPayload(fields, answersStore) {
      const payload = {};
      fields.forEach((field) => {
        const value = answersStore[field];
        if (value !== undefined && value !== null && String(value).trim() !== "") {
          payload[field] = field === "event_datetime" ? fromDatetimeLocalValue(value) || value : value;
        }
      });
      return payload;
    },

    async previewTicket() {
      this.error = "";
      if (!this.rawText.trim()) {
        this.error = "Введите текст заявки";
        return;
      }

      this.loading = true;
      try {
        const data = await apiRequest("/tickets/preview", "POST", { raw_text: this.rawText.trim() });
        this.applyPreviewResponse(data);
        showToast("Заявка обработана — проверьте данные", "success");
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },

    async submitPreviewAnswers() {
      this.error = "";
      if (!this.previewActive) {
        this.error = "Сначала проверьте заявку";
        return;
      }

      const payload = this.buildAnswersPayload(this.previewMissingFields, this.previewAnswers);
      if (!Object.keys(payload).length) {
        this.error = "Заполните хотя бы одно поле для уточнения";
        return;
      }

      this.loading = true;
      try {
        const data = await apiRequest("/tickets/preview/clarify", "POST", {
          raw_text: this.rawText.trim(),
          extracted: this.previewExtracted,
          answers: payload,
        });
        this.applyPreviewResponse(data);
        showToast(
          data.missing_fields?.length
            ? "Данные обновлены — заполните оставшиеся поля"
            : "Все поля заполнены — можно отправить заявку",
          "success"
        );
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },

    async confirmTicket() {
      this.error = "";
      if (!this.rawText.trim()) {
        this.error = "Введите текст заявки";
        return;
      }
      if (!this.previewActive) {
        this.error = "Сначала проверьте заявку";
        return;
      }
      if (this.previewMissingFields.length > 0) {
        this.error = "Уточните все поля перед отправкой";
        return;
      }

      this.loading = true;
      try {
        const data = await apiRequest("/tickets/", "POST", {
          raw_text: this.rawText.trim(),
          extracted: this.previewExtracted,
        });
        this.applyTicketResponse(data);
        showToast("Заявка отправлена", "success");
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },
  }));
});
