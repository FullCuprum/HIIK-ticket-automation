document.addEventListener("alpine:init", () => {
  Alpine.data("employeesPage", () => ({
    items: [],
    skillOptions: [],
    averageWorkload: 0,
    loading: false,
    saving: false,
    error: "",
    showForm: false,
    editingId: null,
    form: {
      full_name: "",
      position: "",
      skillsText: "",
      max_parallel_tasks: 1,
      is_active: true,
      work_start_hour: 9,
      work_end_hour: 18,
      phone: "",
      email: "",
    },

    init() {
      if (!guardPage(["manager"])) return;
      this.loadEmployees();
      this.loadSkillOptions();
    },

    skillLabel(skill) {
      return SKILL_LABELS[skill] || skill;
    },

    workloadClass(percent) {
      if (percent >= 85) return "bg-red-100 text-red-700";
      if (percent >= 60) return "bg-amber-100 text-amber-700";
      return "bg-emerald-100 text-emerald-700";
    },

    resetForm() {
      this.editingId = null;
      this.form = {
        full_name: "",
        position: "",
        skillsText: "",
        max_parallel_tasks: 1,
        is_active: true,
        work_start_hour: 9,
        work_end_hour: 18,
        phone: "",
        email: "",
      };
    },

    openCreateForm() {
      this.resetForm();
      this.showForm = true;
    },

    openEditForm(employee) {
      this.editingId = employee.id;
      this.form = {
        full_name: employee.full_name,
        position: employee.position,
        skillsText: (employee.skills || []).join(", "),
        max_parallel_tasks: employee.max_parallel_tasks,
        is_active: employee.is_active,
        work_start_hour: employee.work_start_hour,
        work_end_hour: employee.work_end_hour,
        phone: employee.phone || "",
        email: employee.email || "",
      };
      this.showForm = true;
    },

    parseSkills() {
      return this.form.skillsText
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    },

    buildPayload() {
      return {
        full_name: this.form.full_name.trim(),
        position: this.form.position.trim(),
        skills: this.parseSkills(),
        max_parallel_tasks: Number(this.form.max_parallel_tasks),
        is_active: Boolean(this.form.is_active),
        work_start_hour: Number(this.form.work_start_hour),
        work_end_hour: Number(this.form.work_end_hour),
        phone: this.form.phone.trim() || null,
        email: this.form.email.trim() || null,
      };
    },

    async loadSkillOptions() {
      try {
        this.skillOptions = await apiRequest("/employees/skills");
      } catch (error) {
        showToast(error.message, "error");
      }
    },

    async loadEmployees() {
      this.loading = true;
      this.error = "";
      try {
        const data = await apiRequest("/employees/");
        this.items = data.items || [];
        this.averageWorkload = data.average_workload_percent || 0;
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },

    async saveEmployee() {
      this.saving = true;
      this.error = "";
      try {
        const payload = this.buildPayload();
        if (this.editingId) {
          await apiRequest(`/employees/${this.editingId}`, "PUT", payload);
          showToast("Сотрудник обновлён", "success");
        } else {
          await apiRequest("/employees/", "POST", payload);
          showToast("Сотрудник добавлен", "success");
        }
        this.showForm = false;
        this.resetForm();
        await this.loadEmployees();
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.saving = false;
      }
    },

    async deactivateEmployee(employeeId) {
      if (!confirm("Деактивировать сотрудника?")) return;
      this.loading = true;
      try {
        await apiRequest(`/employees/${employeeId}`, "DELETE");
        showToast("Сотрудник деактивирован", "success");
        await this.loadEmployees();
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },
  }));
});
