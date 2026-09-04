// --- App.tsx ---

import { Refine, useIsAuthenticated } from "@refinedev/core";
import dataProvider from "@refinedev/simple-rest";
import routerBindings, { NavigateToResource } from "@refinedev/react-router-v6";
import {
    BrowserRouter,
    Routes,
    Route,
    Outlet,
    Navigate,
} from "react-router-dom";
import { ConfigProvider, Spin } from "antd";
import ruRU from "antd/locale/ru_RU";
import "dayjs/locale/ru";
import "antd/dist/reset.css";
import { categories } from "./config/menu";
import { BRAND, ANT_PRIMARY } from "./config/colors";
import { Sidebar } from "./components/layout/Sidebar";
import { GenericList } from "./pages/GenericList";
import { Login } from "./pages/Login";
import { Users } from "./pages/Users";
import { ResidentCabinet } from "./pages/ResidentCabinet";
import { AdminCabinet } from "./pages/AdminCabinet";
import { CashReport } from "./pages/CashReport";
import { ExpenseReport } from "./pages/ExpenseReport";
import { DebtorsReport } from "./pages/DebtorsReport";
import { StatementReport } from "./pages/StatementReport";
import { authProvider } from "./auth/authProvider";
import { apiUrl, http } from "./auth/http";
import { filterCategoriesByRole } from "./auth/menuAccess";
import { getIdentity } from "./auth/token";

const resourceForRoute = (key: string) => {
    if (key === "users") return <Users />;
    if (key === "cabinet") return <ResidentCabinet />;
    if (key === "cabinet_admin") return <AdminCabinet />;
    if (key === "cash_report") return <CashReport />;
    if (key === "expense_report") return <ExpenseReport />;
    if (key === "debtors_report") return <DebtorsReport />;
    if (key === "statement_report") return <StatementReport />;
    return <GenericList resourceName={key} />;
};

// Обёртка защищённых страниц: если нет авторизации — на /login.
const ProtectedLayout = () => {
    const { data, isLoading } = useIsAuthenticated();
    const authenticated = data?.authenticated === true;

    if (isLoading) {
        return (
            <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Spin size="large" />
            </div>
        );
    }
    if (!authenticated) {
        return <Navigate to="/login" replace />;
    }
    return (
        <div style={{ display: "flex", minHeight: "100vh" }}>
            <Sidebar />
            <div style={{ flex: 1, padding: "40px", background: "#f2f8f3" }}>
                <Outlet />
            </div>
        </div>
    );
};

const App = () => {
    // Ресурсы, видимые текущему пользователю (сокрытие меню/роутов по роли).
    const role = getIdentity()?.role ?? "";
    const visibleCategories = filterCategoriesByRole(role, categories);
    const visibleItems = visibleCategories.flatMap((c) => c.items);
    const defaultResource = visibleItems[0]?.key ?? "owners";

    return (
        <ConfigProvider
            locale={ruRU}
            theme={{
                token: {
                    colorPrimary: ANT_PRIMARY,
                    colorLink: ANT_PRIMARY,
                    colorInfo: BRAND.primary,
                },
                components: {
                    Layout: {
                        bodyBg: "#f4faf5",
                    },
                    Table: {
                        rowHoverBg: "rgba(34,174,46,0.08)",
                        headerBg: "#e3f3e6",
                        headerColor: "#0f4d38",
                        headerSortActiveBg: "#d5eedb",
                    },
                },
            }}
        >
            <BrowserRouter>
                <Refine
                    dataProvider={dataProvider(apiUrl, http)}
                    authProvider={authProvider}
                    routerProvider={routerBindings}
                    resources={visibleItems.map((r) => ({
                        name: r.key,
                        list: `/${r.key}`,
                    }))}
                >
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route element={<ProtectedLayout />}>
                            <Route
                                index
                                element={<NavigateToResource resource={defaultResource} />}
                            />
                            {visibleItems.map((r) => (
                                <Route
                                    key={r.key}
                                    path={`/${r.key}`}
                                    element={resourceForRoute(r.key)}
                                />
                            ))}
                        </Route>
                    </Routes>
                </Refine>
            </BrowserRouter>
        </ConfigProvider>
    );
};

export default App;
