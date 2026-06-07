#!/usr/bin/env bash

# Renk Kodları (Terminal çıktılarını özelleştirmek için)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # Renk Yok (Sıfırlama)

clear
echo -e "${CYAN}===================================================================${NC}"
echo -e "${CYAN}             REHBERE VE ÖRNEK KULLANIMLARA HOŞ GELDİNİZ             ${NC}"
echo -e "${CYAN}===================================================================${NC}"
echo ""
echo -e "${BLUE}Bu betiğin temel amacı, pipeline kullanım mantığını${NC}"
echo -e "${BLUE}ve parametrelerini kolayca anlamanızı sağlamaktır.${NC}"
echo ""
echo -e "${YELLOW}(NOT: Bu script simülasyonu başlatmaz, sadece sizi eğitmeyi amaçlar.)${NC}"
echo ""
echo -e "Bu pipeline, GROMACS'ın karmaşık ve kafa karıştırıcı adımlarıyla"
echo -e "tek tek uğraşmak istemeyen kullanıcılar için tasarlanmıştır. Ancak işin"
echo -e "mantığını en iyilerden öğrenmek her zaman en doğru pratik yöntemdir."
echo ""
echo -e "Yeni başlayanlar için profesyonel GROMACS rehberine şuradan ulaşabilirsiniz:"
echo -e ">>  ${GREEN}mdtutorials.com/gmx${NC}  <<"
echo -e "Oradaki her adımı iyice anlamanız ilerisi için faydalı olacaktır."
echo ""
echo -e "${CYAN}-------------------------------------------------------------------${NC}"
read -p "Devam etmek için [y] veya [Y] tuşuna basın... " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo -e "\n${RED}Sonra görüşmek üzere!${NC}"
  exit 1
fi

echo -e "\n\n\n\n\n\n"
echo -e "${YELLOW}[ADIM 1]: Sanal Ortamı Aktif Etme${NC}"
echo -e "Bu Python 3 ile yazılmıştır. Bu yüzden scripti çalıştırmadan"
echo -e "önce oluşturduğumuz Python ortamını aktif etmeniz gerekir."
echo ""
echo -e "Eğer ${CYAN}'conda.install'${NC} ve ${CYAN}'docker.install'${NC} adımlarını tamamladıysanız,"
echo -e "Sisteminizde ${GREEN}'md_env'${NC} adında bir sanal ortam hazır bulunmalıdır."
echo ""
echo -e "İş akışını başlatmadan önce şu komutla ortamı aktif edin:"
echo -e ">>  ${YELLOW}conda activate md_env${NC}  <<"
echo ""
echo -e "${CYAN}-------------------------------------------------------------------${NC}"
read -p "Bir sonraki adıma geçmek için [y/n]? " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo -e "\n${RED}Sonra görüşmek üzere!${NC}"
  exit 1
fi

echo -e "\n\n\n\n\n\n"
echo -e "${YELLOW}[ADIM 2]: Yardım Menüsünü ve Parametreleri İnceleme${NC}"
echo -e "Harika, sanal ortamımız hazır. Şimdi scriptin bizden hangi argümanları"
echo -e "beklediğini görmek için yardım komutuna göz atalım."
echo ""
echo -e "Normalde terminale şu komutu yazarak görebilirsiniz:"
echo -e ">>  ${YELLOW}python3 main.py workflow --help${NC}  <<"
echo -e "${BLUE}(Merak etmeyin, script bu çıktıyı sizin için aşağıya yazdıracaktır)${NC}"
echo ""
echo -e "${CYAN}-------------------------------------------------------------------${NC}"
read -p "Yardım mesajını görüntülemek için [y] tuşuna basın. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo -e "\n${RED}Sonra görüşmek üzere!${NC}"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

# Help çıktısının simülasyonu
cat <<'EOF'
usage: main.py workflow [-h] [--config CONFIG] [--protein PROTEIN [PROTEIN ...]]
                      [--ligand LIGAND [LIGAND ...]] [--outdir OUTDIR]
                      [--workdir WORKDIR] [--gpu] [--no-gpu] [--docker]
                      [--no-docker] [--image IMAGE] [--skip-prep]

Automated MD Workflow for Protein-Ligand Complexes

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG   Path to config file
  --protein, -p PROTEIN [PROTEIN ...]
                        Protein files (PDB/PDBQT) or directories
  --ligand, -l LIGAND [LIGAND ...]
                        Ligand files (SMILES/PDBQT/MOL2) or directories
  --outdir, -o OUTDIR   Output directory
  --workdir, -w WORKDIR
                        Working directory
  --gpu                 Enable GPU acceleration
  --no-gpu
  --docker              Run via Docker
  --no-docker
  --image IMAGE         Docker image
  --skip-prep           Skip ligand and protein preparation steps
EOF

echo ""
echo -e "${GREEN}Yardım mesajını başarıyla inceledik.${NC}"
echo -e "Şimdi simülasyon fiziksel parametrelerini barındıran ${YELLOW}'config.json'${NC} yapısına bakalım."
echo -e "Normalde terminalde göreceğiniz çıktı: >> ${YELLOW}cat config.json${NC} <<"
echo ""
echo -e "${CYAN}-------------------------------------------------------------------${NC}"
read -p "Konfigürasyon dosyasını görmek için [y] tuşuna basın. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo -e "\n${RED}Sonra görüşmek üzere!${NC}"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

# JSON simülasyonu
cat <<'EOF'
{
  "proteins": [{ "file": "5TBM.pdb", "id": "5TBM" }],
  "ligands": [
    {
      "file": "leads/5TBM_COMBINED-SCREENED-MOLECULES-35019-LOW_34389.pdbqt",
      "id": "COMBINED-SCREENED-MOLECULES-35019-LOW_34389",
      "SMILES": "O=C1CC=C(C=C1)c1nn(c2ccccc2)c(=O)c2c1cccc2"
    }
  ],
  "em": { "nsteps": 50000, "emtol": 1000.0, "emstep": 0.01 },
  "nvt": { "nsteps": 50000, "dt": 0.002, "tau_t": 0.1 },
  "npt": { "nsteps": 50000, "dt": 0.002, "tau_t": 0.1, "tau_p": 2.0 },
  "md": {
    "nsteps": 500000, "dt": 0.002, "tau_t": 0.1, "tau_p": 2.0,
    "nstxout": 0, "nstvout": 0, "nstfout": 0, "nstxtcout": 5000,
    "nstenergy": 5000, "nstlog": 5000
  }
}
EOF

echo ""
echo -e "${BLUE}Burada etkileşim halinde olan çok fazla parametre var.${NC}"
echo -e "Endişelenmeyin! Bu rehber hepsinin tam olarak ne anlama geldiğini açıklayacak."
echo ""
echo -e "${CYAN}-------------------------------------------------------------------${NC}"
read -p "Parametre detaylarını okumak için [y] tuşuna basın. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo -e "\n${RED}Sonra görüşmek üzere!${NC}"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

# Detaylı parametre açıklamalarının Türkçe karşılıkları
cat <<'EOF'
----------------------------------------------------------------
KONFİGÜRASYON AYARLARININ DETAYLI ANALİZİ (config.json)
----------------------------------------------------------------
Bu dosya; yapısal algoritmaları, ortamı ve fizik sabitlerini koordine eder.

A. Sistem Ortamı ve Parametre Fiziği:
* force_field ("amber99sb-ildn"): Atomların ve moleküler bağların davranışlarını
  hesaplamak için kullanılan matematiksel enerji denklemlerini (Kuvvet Alanı) belirler.
* water_model ("tip3p"): Sisteminizi çözündürmek (solvasyon) için klasik, rijit 
  3 noktalı su molekülü matrisini uygular.
* box_type ("cubic") & box_buffer (1.0): Protein-ligand yapısını kübik bir kutuya 
  yerleştirir ve sınırlarına 1.0 nm güvenlik mesafesi ekler. Böylece makromolekül 
  periyodik görüntülerde kendi kendisiyle etkileşime girip simülasyonu bozmaz.

B. Elektrostatik ve Sınırlar:
* coulombtype ("PME"): Uzun menzilli elektrostatik kuvvetleri sistemi yavaşlatmadan 
  kesin ve hassas bir şekilde hesaplamak için Particle Mesh Ewald yöntemini kullanır.
* cutoff_scheme ("Verlet"): Hangi atomların birbirine non-bonded (bağsız) kuvvet 
  uygulayacak kadar yakın olduğunu çözen grid tabanlı komşuluk listesi motorudur.

C. Detaylı Simülasyon Aşamaları:
* em (Enerji Minimizasyonu): Yapıyı rahatlatır. Yapısal kuvvetler tolerans eşiğinin 
  (emtol: 1000.0) altına inene kadar küçük adımlarla (emstep: 0.01) sistemi optimize eder.
* nvt (Sabit Madde Miktarı, Hacim, Sıcaklık): Zaman adımı ölçeğini (dt: 0.002 ps) 
  kullanarak sisteminizi 300K sıcaklığa güvenli bir şekilde ısıtır.
* npt (Sabit Madde Miktarı, Basınç, Sıcaklık): İzotropik ölçekleme kullanarak 
  sistem basıncını 1.0 bar seviyesinde dengeler (compressibility: 4.5e-5).
* md (Üretim Simülasyonu): Verilerin toplandığı son adımdır. Gerçek yapısal hareketin 
  500.000 adımını simüle eder; her 5.000 adımda bir koordinatları (nstxtcout) ve enerjiyi kaydeder.

EOF

echo "Bunlar GROMACS'ın çalışması için ihtiyaç duyduğu parametrelerdir."
echo "Ancak şu an onlara çok takılmamıza gerek yok."
echo "Gelin bu pipeline için bizim adımıza en önemli olan kısımlara bakalım."
echo ""
echo -e "${CYAN}-------------------------------------------------------------------${NC}"
read -p "Molekül girdi formatlarını öğrenmek için [y] tuşuna basın. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo -e "\n${RED}Sonra görüşmek üzere!${NC}"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

echo -e "Dosyanın içinde bizim düzenleyeceğimiz 2 ana alan var:"
echo -e "${GREEN}'proteins'${NC} ve ${GREEN}'ligands'${NC}. Bunlar obje listesi (array) alırlar."
echo "Yapıları şu şekildedir:"
cat <<'EOF'
  proteins: [
    { "file": "pdbs/protein.pdb",
        // ^^^^^^^^^^^ Dosya yolu config.json dosyasına göre bağıl (relative) olmalıdır.
        // Örnek dosya ağacı görünümü:
        //        | config.json
        //        | pdbs/
        //        --| protein.pdb
        //        --| ligand.pdbqt
        //        | main.py workflow
        //
        // Bu ağaç yapısında protein.pdb dosyası şu şekilde tanımlanır:
        //          "file": "pdbs/protein.pdb"

      "id": "5TBM" // Moleküle ait benzersiz (unique) bir isim/kod.
    }
  ],

EOF
echo -e "Protein için iki önemli alan: ${YELLOW}'id'${NC} ve ${YELLOW}'file'${NC}."
echo "Şimdi ligandların nasıl ekleneceğine bakalım:"
echo ""
echo -e "${CYAN}-------------------------------------------------------------------${NC}"
read -p "Ligand tanımlamalarını görmek için [y] tuşuna basın. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo -e "\n${RED}Sonra görüşmek üzere!${NC}"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

cat <<'EOF'
  ligands: [
    { "file": "pdbs/ligand.pdbqt",
        // ^^^^^^^^^^^ Config dosyasına göre bağıl konumdur. Mantığı protein ile aynıdır.
        // ÖNEMLİ: Bu dosya protein ile hizalanmış yerleşim (docking pose) koordinatlarını
        // içermelidir. Yani bu aşamadan önce docking işlemini yapmış olmanız gerekir.

      "id": "benzersiz-ligand-adi", 
      "SMILES": "O=C(c1nn(C)c(=O)c2c1cccc2)Nc1cccc2c1cccc2" 
        // ^^^^^^ Ligandın SMILES formatındaki dizilimi.
        // Eğer GROMACS hazırlık aşamasında moleküler format dönüşümü başarısız olursa
        // yedek plan olarak bu SMILES verisi kullanılır.
    },
    { "file": ... // İstediğiniz kadar ligandı alt alta nesne olarak ekleyebilirsiniz.
    } // <-- UYARI: Son elemandan sonraki virgülü (comma) kaldırmayı unutmayın, JSON hata verir.
  ],

EOF
echo -e "${CYAN}-------------------------------------------------------------------${NC}"
read -p "Komut satırı (CLI) argümanlarını incelemek için [y] tuşuna basın. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo -e "\n${RED}Sonra görüşmek üzere!${NC}"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

cat <<'EOF'
----------------------------------------------------------------
KOMUT SATIRI ARGÜMANLARI (main.py workflow)
----------------------------------------------------------------
Terminalden doğrudan parametreler vererek iş akışını kontrol edebilirsiniz:

* --config (-c): JSON konfigürasyon dosyanızın yolunu belirtir.
* --protein (-p) & --ligand (-l): Dosyaları doğrudan terminalden beslemenizi sağlar.
  Tek bir dosya yolu veya taranan moleküllerin olduğu bir klasörü gösterebilirsiniz.
* --gpu / --no-gpu: GROMACS'ın NVIDIA ekran kartınızı kullanıp kullanmayacağını seçer.
  WSL üzerinde adımların katlarca hızlı bitmesi için --gpu her zaman önerilir.
* --docker / --no-docker: Python scriptine komutları yerel kütüphanelerle mi yoksa
  izole bir Docker konteyneri içinde mi çalıştıracağını söyler.

EOF
echo -e "${CYAN}-------------------------------------------------------------------${NC}"
read -p "Bitirmek için [y] tuşuna basın. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo -e "\n${RED}Sonra görüşmek üzere!${NC}"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

echo -e "${GREEN}Şimdilik bu kadar! İlk GPU destekli Docker simülasyonunuzu başlatmaya hazırsınız:${NC}"
echo ""
echo -e ">>  ${YELLOW}python3 main.py workflow -c config.json -w work/ -o results --gpu --docker${NC}  <<"
echo ""
echo -e "${GREEN}Her şey tamam! Yolunuz açık olsun!${NC}"
