document.addEventListener("alpine:init", () => {
  Alpine.data("usersPage", () => ({
    items: [],
    loading: false,
    saving: false,
    error: "",
    showForm: false,
    editingId: null,
    form: {
      username: "",
      password: "",
      role: "user",
      is_active: true,
    },

    init() {
      if (!guardPage(["admin", "manager"])) return;
      this.loadUsers();
    },

    roleLabel(role) {
      return USER_ROLE_LABELS[role] || role;
    },

    resetForm() {
      this.form = {
        username: "",
        password: "",
        role: "user",
        is_active: true,
      };
    },

    openCreateForm() {
      this.editingId = null;
      this.resetForm();
      this.showForm = true;
    },

    openEditForm(user) {
      this.editingId = user.id;
      this.form = {
        username: user.username,
        password: "",
        role: user.role,
        is_active: user.is_active,
      };
      this.showForm = true;
    },

    async loadUsers() {
      this.loading = true;
      this.error = "";
      try {
        this.items = await apiRequest("/users/");
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },

    buildPayload() {
      const payload = {
        username: this.form.username.trim(),
        role: this.form.role,
      };

      if (this.editingId) {
        payload.is_active = this.form.is_active;
        if (this.form.password.trim()) {
          payload.password = this.form.password;
        }
        return payload;
      }

      payload.password = this.form.password;
      return payload;
    },

    async saveUser() {
      this.saving = true;
      this.error = "";
      try {
        const payload = this.buildPayload();
        if (this.editingId) {
          await apiRequest(`/users/${this.editingId}`, "PUT", payload);
          showToast("Пользователь обновлён", "success");
        } else {
          if (!payload.password) {
            throw new Error("Укажите пароль для нового пользователя");
          }
          await apiRequest("/users/", "POST", payload);
          showToast("Пользователь создан", "success");
        }
        this.showForm = false;
        await this.loadUsers();
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.saving = false;
      }
    },

    async deleteUser(user) {
      if (!confirm(`Удалить пользователя ${user.username}?`)) {
        return;
      }

      try {
        await apiRequest(`/users/${user.id}`, "DELETE");
        showToast("Пользователь удалён", "success");
        await this.loadUsers();
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      }
    },
  }));
});
