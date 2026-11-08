import { Button, Group } from "@mantine/core";
import { IconMapOff } from "@tabler/icons-react";
import { Link, Route, Routes } from "react-router-dom";
import { AlertsBanner } from "./components/AlertsBanner";
import { Layout } from "./components/Layout";
import { MonthSelector } from "./components/MonthSelector";
import { QuickEntryButton } from "./components/QuickEntry";
import { ThemeToggle } from "./components/ThemeToggle";
import { EmptyState } from "./components/ui/EmptyState";
import { CatalogPage } from "./pages/Catalog/CatalogPage";
import { HelpPage } from "./pages/Help/HelpPage";
import { InvestmentsPage } from "./pages/Investments/InvestmentsPage";
import { ProfilesPage } from "./pages/Profiles/ProfilesPage";
import { ProjectionPage } from "./pages/Projection/ProjectionPage";
import { ReceivablesPage } from "./pages/Receivables/ReceivablesPage";
import { ReviewPage } from "./pages/Review/ReviewPage";
import { SettingsPage } from "./pages/Settings/SettingsPage";
import { StatusPage } from "./pages/Status/StatusPage";
import { SummaryPage } from "./pages/Summary/SummaryPage";
import { TransactionsPage } from "./pages/Transactions/TransactionsPage";

export function App() {
  return (
    <Layout
      header={
        <Group gap="sm" wrap="nowrap" className="et-header__controls">
          <MonthSelector />
          <QuickEntryButton />
          <ThemeToggle />
        </Group>
      }
      drawerFooter={<ThemeToggle />}
      banner={<AlertsBanner />}
    >
      <Routes>
        <Route path="/" element={<SummaryPage />} />
        <Route path="/projecao" element={<ProjectionPage />} />
        <Route path="/lancamentos" element={<TransactionsPage />} />
        <Route path="/revisao" element={<ReviewPage />} />
        <Route path="/a-receber" element={<ReceivablesPage />} />
        <Route path="/investimentos" element={<InvestmentsPage />} />
        <Route path="/cadastros" element={<CatalogPage />} />
        <Route path="/perfis" element={<ProfilesPage />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="/configuracoes" element={<SettingsPage />} />
        <Route path="/ajuda" element={<HelpPage />} />
        <Route
          path="*"
          element={
            <EmptyState
              icon={<IconMapOff size={26} stroke={1.6} />}
              title="Página não encontrada"
              description="O endereço não existe neste app."
              action={
                <Button component={Link} to="/" variant="light" mt="xs">
                  Ir para o Resumo
                </Button>
              }
            />
          }
        />
      </Routes>
    </Layout>
  );
}
